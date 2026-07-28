---
title: "Story personalization: implementation plan"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Phased implementation plan for ADR-023 (guardian opt-in, render-time story
  personalization): the sentinel-bound slot kind, the post-fill sentinel-integrity check and its
  QA strategy, the leak-surface guard points, the server-side slot-value schema, the API surface,
  the client-side resolver, the ring-2 cross-family delivery mechanism, the dedication-line
  overlay, the kid-facing control, migration, erasure, and the risk register."
tags:
  - planning
  - implementation
  - privacy
  - generation
  - frontend
component: Strategy
source: "ADR-023 (render-time story personalization); owner decision round 2026-07-25
  (OD-1 through OD-5); current-state exploration of api/recommendations.py, api/deps.py,
  db/models.py, api/profiles.py, api/schemas.py, and frontend/src/offline/."
---

# Story personalization: implementation plan

> **Status**: Draft (2026-07-25). Blocked on [ADR-023](./adr/adr-023-story-personalization-slots.md)
> flipping from Proposed to Accepted. **Every owner-level decision it was waiting on is now
> closed** (the 3-5 band question and OD-1 through OD-5, all confirmed by owner choice 2026-07-25);
> what remains is counsel confirmation on OD-1 and OD-5, which should land before P7 and P9 ship
> but blocks no earlier phase. Ring 2 is in scope and designed end to end in section 8.
> **Decision record**: [ADR-023](./adr/adr-023-story-personalization-slots.md)
> **Date**: 2026-07-25

## 0. What this plan assumes

Read ADR-023 first. The one-line summary this plan builds on: the server always stores and serves
a generic, sentinel-bearing story blob, identical for every viewer; a small per-profile values
payload is resolved **client-side at render time** and never persisted into story content, never
sent to any provider, and never baked into a blob.

Nothing in this feature exists in code today. Every file reference below is either a file to
change or a file whose current behaviour is the reason a change is needed. Line numbers were
verified against the working tree on 2026-07-25 (branch `claude/children-data-privacy-gdpr-8mxlxx`,
HEAD `79e10c5`) and should be re-checked before use, since several of these files are actively
edited by other workstreams.

## 1. Phase ordering and why

Dependencies force most of the order. The rule of thumb: **nothing user-visible can ship before
the sentinel mechanism exists**, because a toggle with no sentinel to resolve is a toggle over
nothing, and a values payload with no integrity check behind it is an unaudited injection path.

| Phase | Deliverable | Depends on | Ships anything user-visible? |
|---|---|---|---|
| **P1** | Sentinel-bound slot kind; fill-time and storage-time preservation (section 2) | Nothing | No |
| **P2** | Post-fill sentinel-integrity check and its QA/retry strategy (section 3) | P1 | No |
| **P3** | Leak-surface guard points and their tests (section 4) | P1 | No |
| **P4** | Data model: slot values, toggles, consent records, eligibility flags (section 5) | **P2** (3.4's survival measurement gates whether this is worth building at all); scope settled by ADR-023 OD-1/OD-2/OD-5 (all confirmed 2026-07-25) | No (schema only) |
| **P5** | API surface plus OpenAPI client regeneration (section 6) | P4 | No (contract only) |
| **P6** | Client-side resolver in `frontend/src/player/`; ring-1 values payload; offline interaction (section 7) | P1, P3, P5 | Yes, behind `VITE_FEATURE_PERSONALIZATION` |
| **P7** | Ring-2 cross-family delivery: endpoint, authz predicate, client fetch (section 8) | P5, P6 | Yes, same flag |
| **P8** | Dedication-line title-page overlay (section 9) | P4, P6 | Yes, same flag |
| **P9** | Guardian toggle UI; ring-2 consent capture; kid-facing control (section 10) | P4, P6, P7, **and the P11 Route A copy fix as an exit criterion** (see below) | Yes |
| **P10** | Catalog migration: repair or replace existing test content (section 11) | P1, P2 | No |
| **P11** | Route A copy wiring (text already drafted per OD-3); erasure, export, privacy-notice and classification updates (section 12) | P9, and the copy half is itself a P9 exit criterion | Yes (copy) |

P3 can run in parallel with P2. P10 can run any time after P2 and should not gate P6, since P6 can
be developed against a small number of freshly generated sentinel-bearing stories. P8 shares
nothing with the sentinel work and can slip without blocking anything else.

**Two ordering constraints that are easy to get wrong, called out because an earlier draft got both
wrong:**

- **The Route A copy fix is not a P11 cleanup, it is a P9 gate.** P11 rewrites the kid-facing
  "Heroes in our stories always have made-up names" strings
  (`story_requests/interpretation.py:1017-1035`). If that lands after P9, the app ships a live
  toggle that makes an absolute on-screen claim false for every family that flips it. The rule:
  **`VITE_FEATURE_PERSONALIZATION` may not be enabled in any environment where a real family can
  reach it until the copy fix has merged.** Treat the copy change as an exit criterion on P9 and a
  precondition on the flag, not as documentation debt.
- **P4 waits on P2, not P1.** Section 3.4 measures whether sentinels actually survive the fill LLM.
  That measurement can invalidate the whole approach, so building the data model, the consent
  tables, and the migrations before it lands risks schema work for a mechanism that does not
  function. P1 plus P2 plus the 3.4 numbers is the real gate on committing to the rest.

Two cross-cutting obligations that are not phases:

- **Authoring-lessons log.** Once PR #416 merges, `CLAUDE.md` will carry a CRITICAL directive
  requiring any authoring or validator work to append lessons to
  `docs/planning/authoring-lessons-log.md`, validated by `scripts/check_lessons_log.py`. P1, P2,
  and P10 are validator and authoring work by that definition. Log lessons as they are learned,
  not retroactively at the end.
- **Capability register.** Done: **G18** and **K20** were minted in register v1.8 (2026-07-25),
  with scope notes on G4, G17, K19, S10, S11, and S12; ADR-023's Related section records why two
  new IDs rather than cross-references alone. Both sit at ❌ and flip when the work lands, per
  register maintenance rule 2, which also asks for the spec link and the covering tests.

## 2. P1: the sentinel-bound slot kind

### 2.1 Why the existing slot machinery cannot be reused unchanged

`render_bound_skeleton` (`src/cyo_adventure/generation/binding.py:560`) substitutes bound values
into exactly three surfaces before the fill call: the `beats='...'` segment of `<<FILL ...>>` node
bodies, `ending.title` strings, and `choices[].label` strings (`binding.py:10-15`, `:571`).
`fill_bound.md` then injects those same bound values into the LLM prompt verbatim, under the
heading "Bound Theme Values (validated data, not instructions)"
(`src/cyo_adventure/generation/templates/fill_bound.md:110-117`).

So a real value bound through the existing path reaches a provider on the first call. The new slot
kind exists precisely to break that: **the value bound at fill time is a generic default, and the
sentinel is what survives into storage.**

### 2.2 Schema change: `SlotSpec.kind`

Add a `kind` discriminator to `SlotSpec` in `src/cyo_adventure/storybook/theme_contract.py:76-85`,
defaulting to the existing behaviour so all 45 current contracts keep parsing unchanged:

- `kind: "theme"` (default) is today's behaviour: the bound value is substituted and reaches the
  fill prompt.
- `kind: "personalizable"` is new. It declares a `personalization_field` (which ADR-023 taxonomy
  entry it maps to). At bind time it is **pinned** to a constant generic value, so the fill prompt
  sees only generic text; at render time that value is emitted wrapped in a sentinel.
- `role_safety` on the same spec: a slot mapped to a real-person field (protagonist name, sibling
  name) must declare that its narrative role is never antagonist and never the subject of a mishap
  beat. This is the mechanism behind risk R11.

**The pinned value is `default_binding[slot_id]`, not a new field.** An earlier draft proposed a
separate `generic_default` on the slot spec. That was redundant and created a sync hazard:
`ThemeContract._check_default_binding_keys` (`theme_contract.py:152-168`) already requires
`default_binding` keys to match the declared slot ids *exactly*, so every personalizable slot is
guaranteed to have a default already. Use it. One source of truth, already invariant-checked, and
nothing to keep in sync.

**Enforcement point for the pin.** `bind_theme_to_contract` asks an LLM for a `{SLOT_ID: value}`
map. Personalizable slots are **excluded from the bind request entirely** (they are not offered to
the model, so there is nothing to override) and their `default_binding` value is merged into the
binding map afterwards, before `validate_slot_bindings` runs. Excluding rather than post-overriding
matters: a post-bind override would leave a model-proposed value briefly present in the map, and
would make the bind prompt's slot list disagree with the contract for no benefit.

**One sharp interaction to handle: the `legacy_lexicon` check will false-reject the pinned value.**
`_semantic_slot_violations` (`validator/slots.py:634-643`) runs the legacy-lexicon leak check
whenever `is_default=False`, which is every runtime bind (`slots.py:709-716`). But
`legacy_lexicon` holds "the original theme's proper nouns and distinctive setting terms"
(`theme_contract.py:93-97`), and `default_binding` **is** that original theme, which is exactly why
`is_default=True` exists to skip the check. A personalizable slot pinned to its default on a real
runtime bind therefore hits the check with a value that is legitimately in the lexicon, and fails.
Fix: skip `legacy_lexicon` for `kind: "personalizable"` slots, for the identical reason
`is_default` skips it. The check exists to stop a *new* theme reintroducing the old theme's
identity; a slot pinned to a constant proposes nothing, so there is nothing to leak.

`ThemeContract._check_contract_invariants` (`theme_contract.py:120-134`) gains matching
invariants: a `personalizable` slot's `personalization_field` must name an entry on ADR-023's
include list, and a slot mapped to a real-person field must declare `role_safety`.

Note for the implementer: no `.contract.json` in the catalog currently sets `constraints.pattern`,
even though `SlotConstraints` declares it (`theme_contract.py:73`) and `validate_slot_bindings`
enforces it (`src/cyo_adventure/validator/slots.py:645-653`). If the new slot kind wants a
pattern-shaped constraint, it will be the first real user of that code path. Test it directly
rather than assuming it is exercised.

### 2.3 Sentinel format and, crucially, how one gets into the prose

An earlier draft of this plan specified the sentinel *checker* in detail and left the *producer*
undesigned, hand-waving it as "add sentinels to the do-not-change list". That does not work, and
the reason it does not work is worth stating before the fix: `fill_bound.md`'s do-not-change list
(`:80-92`) protects **structural JSON fields that are already present in the input** (`id`,
`target`, `condition`, `effects`, `variables`, ending `title`). Node bodies are not in that
category. They arrive as `<<FILL role=... words=... beats='...'>>` directives and leave as
**freshly written prose**, and the prompt explicitly instructs the model to re-imagine that prose
in the theme's own vocabulary (`fill_bound.md:51-60`). You cannot "preserve" a token that was
never in the input. The model has to be told to **emit** it.

#### 2.3.1 Which surfaces carry sentinels, and which deliberately do not

`render_bound_skeleton` touches exactly three surfaces (`binding.py:10-15`, `:563-571`). Each one
needs a separate answer:

| Surface | Sentinels? | Mechanism |
|---|---|---|
| Ending `title` | **Yes** | Substituted at render time and preserved by an **existing** rule: "Ending `title` values are final; do not change them" (`fill_bound.md:90`). No new instruction needed. Highest-reliability surface |
| `beats='...'` inside `<<FILL>>`, producing body prose and dialogue | **Yes**, and this is the main event | Substituted into the beats guidance at render time, then **re-emitted by the model into the prose** under a new prompt rule (2.3.3) |
| `choices[].label` | **No, deliberately** | `fill_bound.md:67` instructs "Phrase each choice label in this theme's own vocabulary; do not reuse a generic label phrasing that ignores the theme", and the Stage 1 label-intent review checks the frozen action-semantic. A verbatim-preservation rule would directly contradict a load-bearing diversity instruction, for a surface where a name adds little. Labels stay generic |

Saying "not choice labels" out loud is part of the design, not a gap. It also simplifies the
checker: labels are excluded from the expected-token computation.

#### 2.3.2 The delimiter, worked through rather than deferred

Four constraints, and one shape satisfies all of them:

1. **Must not match `SLOT_TOKEN_RE`** (`theme_contract.py:34`), which is
   `\{([A-Z][A-Z0-9_]*)\}`. This is not stylistic: `render_bound_skeleton` post-condition 1
   requires "zero `{SLOT}`-shaped tokens remain anywhere in the rendered document"
   (`binding.py:576-578`), so a sentinel that looked like a slot token would fail the render.
2. **Must not be forgeable from a slot value.** `_charset_violations`
   (`validator/slots.py:396-411`) already rejects `{`, `}`, `<<`, `>>` in any bound value.
3. **Must not disturb the FILL directive grammar** (`_FILL_RE`, `binding.py:71`).
4. **Must degrade to correct prose** when markers are stripped.

**Proposed shape: `{~HERO:Explorer~}`.** The reasoning:

- The outer braces make it forgery-proof for free, because braces are already banned in slot values
  (constraint 2), so no value-side path can construct one.
- The interior begins with `~`, which is not `[A-Z]`, so `SLOT_TOKEN_RE` cannot match it at any
  offset (constraint 1). Verified by inspection of the pattern: the only `{` in the token is at
  offset 0, and the character after it is `~`.
- It contains no `<<`, `>>`, or `'`, so it cannot corrupt a directive (constraint 3). Note that
  `render_bound_skeleton` reconstructs `role=`/`words=` from the parsed directive rather than
  copying bytes, precisely so substituted text cannot corrupt the shape (`binding.py:563-567`),
  and the CR-1 invariant (`binding.py:545-558`) proves it did not.
- Stripping `{~HERO:` and `~}` yields exactly `Explorer` (constraint 4). The slot id is carried
  inline, so resolution needs no lookup and an unmatched slot id is self-evidently a defect.
- Practical point for LLM fidelity: a token containing a readable English word survives a
  copy-verbatim instruction far better than an opaque id would. Do not "improve" this into a UUID.

#### 2.3.3 The prompt-instruction change (the actual producer)

Add to `fill_bound.md`, as its own section near the FILL Directive Syntax block:

> **Verbatim tokens.** Some `beats='...'` guidance contains tokens of the form `{~NAME:Word~}`.
> These are placeholders a family may later personalise. For every distinct such token that appears
> in a node's `beats`, your prose for that node must contain that token **at least once**, copied
> character for character, including the braces and tildes. Place it where the word inside it would
> naturally go: in dialogue, in narration, or in an ending title. Do not translate it, do not
> re-theme it, do not add spaces inside it, and do not write the bare word instead of the token. It
> is the one thing in your prose that must be copied rather than re-imagined. Never place one
> inside a choice label.

Two things make this workable rather than hopeful:

- **No new directive grammar.** The token rides inside the existing `beats='...'` text, which
  `render_bound_skeleton` already substitutes into. So `_FILL_RE` (`binding.py:71`),
  `_FILL_WORDS_RE` (`validator/policy.py:44`), and the CR-1 role/words invariant all stay
  untouched. The render's own docstring already scopes substitution this way: "substitution must be
  confined to the beats text inside an unchanged 'role=...words=...' directive"
  (`binding.py:555-557`).
- **It is a per-node contract**, which is exactly what the P2 checker verifies per node. The
  producer and the checker now describe the same object.

#### 2.3.4 Reading-level scoring must strip sentinels

`check_reading_level` tokenizes with `_WORD_RE = [A-Za-z]+(?:['\-][A-Za-z]+)*`
(`validator/reading_level.py:52`, used at `:106`). Against `{~HERO:Explorer~}` that yields **two**
words, `HERO` and `Explorer`, inflating both the word count and the syllable count and skewing the
Flesch-Kincaid grade. Since the gate runs over the stored, sentinel-bearing blob, the reading-level
check must strip sentinels to their inner word before scoring. Add this to P1, not P3: it is a
correctness bug in the gate, not a leak surface.

Record the sentinel pattern in **one** constant, in one module, imported by the validator, the
serializer, and the frontend resolver. See risk R9 for the cheapest cross-language enforcement.

### 2.4 What must not change in P1

- `src/cyo_adventure/generation/pii.py`: no change, no carve-out, no new parameter. This is the
  invariant the whole design exists to preserve.
- `src/cyo_adventure/story_requests/interpretation.py`: no change. Route A stays intact
  (ADR-023 section 4).
- `validate_slot_bindings` (`validator/slots.py:686`): no change to its signature or semantics. It
  validates the generic binding, which is still a binding.

## 3. P2: the sentinel-forgery check

### 3.1 The gap

Nothing today checks that a published blob contains exactly the sentinels its contract declared.
The existing charset rule blocks `{`, `}`, `<<`, `>>` in a bound **value**
(`validator/slots.py:396-411`), which is value-side forgery. Prose-side forgery is uncovered: the
fill LLM writes node bodies freely, and could emit a mutated sentinel, an extra sentinel, a
sentinel in a node that declared none, or drop one entirely. A dropped sentinel degrades quietly
(the reader just sees generic text). An **extra or mutated** sentinel is the real risk: it is an
unreviewed substitution point in prose a human approved believing it was static.

### 3.2 The check

A new deterministic post-fill check, in the same spirit as the four fail-closed post-conditions
`render_bound_skeleton` already carries (`binding.py:578-586`).

**The expected set is computed per node from the pre-fill bound skeleton**: for each node, the set
of distinct sentinel tokens appearing in its `beats='...'` guidance, plus each ending title's own
token. Choice labels are excluded (2.3.1). Given that expectation and the filled blob, assert:

- Per node, the **set of distinct sentinel tokens** in the emitted prose equals the expected set
  for that node. Per-node matters: a sentinel that migrated from node A to node B changes what a
  reader sees where.
- Note this is a **set**, not a multiset, and that is deliberate. The producer contract in 2.3.3
  says "at least once", because a name may naturally recur in a passage and forcing an exact count
  would reject good prose. What must be exact is *which* tokens appear and *that each is
  well-formed*, not how many times.
- Every occurrence is byte-exact: the wrapped text equals the slot's `default_binding` value, the
  slot id resolves to a declared personalizable slot, and no whitespace has crept inside the
  braces. The LLM must not have "improved" the placeholder.
- No sentinel-shaped-but-malformed string appears anywhere in the blob. A near-miss is a stronger
  signal of a problem than a clean absence.
- No sentinel appears in any choice label.

Fail closed: a blob failing this check is discarded exactly as a schema-invalid or gate-failing
repair candidate is today (`src/cyo_adventure/moderation/repair.py:7-13`). It must run **before**
the blob can reach the human approval queue, so the artifact a guardian approves is the artifact
that passed.

Where it hooks in: alongside the existing gate call in `generation/worker.py` (see the
`render_bound_skeleton` call at `worker.py:898` and the post-condition handling at `:867` and
`:1601`) and in `generation/import_story.py:352`, the second `render_bound_skeleton` caller and the
path the `cyo-author` skill uses.

### 3.3 Rescreen and repair interaction

`moderation/rescreen.py` re-reads published blobs and re-runs classifiers over them
(`src/cyo_adventure/api/rescreen.py:1-8`). Sentinels will be present in that text. Two decisions to
make explicitly rather than by accident: whether the classifier sees the sentinel markers or the
stripped generic text (recommendation: **stripped**, so classifier scores stay comparable across
the migration boundary and no classifier sees a token it has no training for), and whether a
rescreen that rewrites nothing can still fail sentinel integrity (recommendation: **yes**, as a
detection signal for corruption at rest).

`moderation/repair.py::attempt_repair` re-prompts the generator to revise prose. Sentinels must be
added to its preserve-list, and the P2 check must re-run on the repaired blob, since
`moderation/pipeline.py` already re-validates and re-gates a repair candidate before adopting it.

### 3.4 QA and measurement: will sentinels actually survive the fill LLM?

This is the single biggest unknown in P1/P2 and it cannot be answered by design. It has to be
measured, and the measurement has to happen **before** P4 onward is scheduled, because a bad
survival rate changes the whole approach.

**What to measure.** Generate a fixed sample (suggested: 30 stories, spread across bands and
across at least 5 skeletons, each with 3 to 6 personalizable slots) and record, per run:

- *Clean-pass rate*: fraction of fills where the sentinel multiset matches exactly on the first
  attempt. This is the number that matters.
- *Failure taxonomy*: dropped, duplicated, relocated (right count, wrong node), mutated wrapper,
  mutated inner text. These have different fixes. Dropping suggests the preserve-list needs
  strengthening; mutation suggests the delimiter is being "corrected" by the model and should be
  changed; relocation suggests the beats guidance is ambiguous about where the slot belongs.
- *Per-provider variance*: run the same sample across at least two of the configured providers
  (`generation/providers/`), because a survival rate that holds on one frontier model and collapses
  on the fallback is a deployment risk, not a curiosity.

**Targets, stated as a position rather than a measured fact.** A clean-pass rate at or above
roughly 95% makes a single retry cheap and the feature viable. Between roughly 80% and 95%, the
feature still works but retries become a real cost line and the delimiter or prompt wording should
be iterated first. Below roughly 80%, reconsider the approach: the fallback is to stop relying on
the LLM to preserve a marker and instead **re-insert sentinels deterministically after the fill**,
by matching the generic-default string in the filled prose. That fallback is less elegant (it can
mis-target if the model used the default word elsewhere) but it removes the model from the
integrity path entirely, and it is worth prototyping in parallel if early numbers are poor.

**Retry policy when the check trips.** One retry, with the failure fed back into the prompt in the
same bounded shape `attempt_repair` already uses for soft-gate findings. A second failure fails the
job rather than retrying again. The rationale is the same as the existing repair budget: an
unbounded retry loop on a non-deterministic step is a cost sink with no convergence guarantee.

**Cost impact, stated plainly.** A fill is the most expensive call in the pipeline. At a 95%
clean-pass rate a single retry adds roughly 5% to fill spend; at 80% it adds roughly 20%. That is
not negligible and it should be visible in the decision to proceed, not discovered on a bill.
Record actual measured numbers in `docs/planning/authoring-lessons-log.md` once PR #416's directive
is live.

**MEASURED 2026-07-28** (`scripts/measure_sentinel_survival.py`, run
`results/sentinel-survival/20260728T205008Z`, 30 stories x 4 slots, first attempt only, the
`fill_bound.md` "Verbatim tokens" preservation instruction present in every prompt):

- **Clean-pass rate: 3.3% (1/30) on `openrouter:anthropic/claude-haiku-4.5`**, which is
  production's primary fill route (`openrouter_model` in `core/config.py`). This is far below
  the ~80% floor: **the below-80% branch applies. G1 verdict: STOP for prompt-only survival.**
  Stage B onward must not proceed on the preserve-through-the-LLM design; the deterministic
  post-fill re-insertion fallback described above graduates from "prototype in parallel" to
  the primary design, and Stage B+ needs re-planning around it.
- Failure taxonomy: dropped 1,738 (dominant by 8x), forged/mutated 207, relocated 111,
  in-choice-label 3, malformed wrapper 7. The dominance of *dropped* means the model simply
  writes prose without the token despite the verbatim instruction; this is not a delimiter
  problem to iterate, it is the model treating the token as guidance rather than payload.
- A one-retry policy at this rate would add ~97% to fill spend, i.e. nearly double every
  fill: economically equivalent to no retry policy at all.
- Caveat: single-provider measurement. The Anthropic direct leg (which would run
  `claude-sonnet-4-6`) was blocked by an account-billing 400 on every trial; per-provider
  variance is unmeasured. A stronger model may score materially higher, but the G1 gate is
  defined on the worst configured provider, and the worst (and primary) provider has now
  been measured at 3.3%.

## 4. P3: leak-surface guard points

Each of these is a concrete place where a sentinel token or a real value could escape. The
architecture makes the **real value** case structurally impossible server-side; these guards are
about the **sentinel** case (an ugly token reaching an external provider or a kid-facing list) and
about defense in depth.

| Surface | File | Current behaviour | Guard to add |
|---|---|---|---|
| Cover-art prompt | `src/cyo_adventure/covers/prompt.py:87-111` | Embeds blob `title`, a protagonist name, and a 240-char opening excerpt (`_opening_excerpt`, `:19-40`) and ships them to an external image provider | Strip sentinels to their generic default before building the prompt. Assert in test that no sentinel marker can appear in a built prompt |
| Recommendation payloads | `src/cyo_adventure/api/recommendations.py:79-94`, `:347` | Surfaces `blob["title"]` as the item title and `rater.display_name` as `recommender_name` | Strip sentinels from the title. Note: `recommender_name` is a separate, already-sanctioned disclosure (ADR-016, and PR #415's B6 decision); do not conflate the two |
| Reading history | `src/cyo_adventure/api/reading_history.py:89`, `:323` | Its own `_book_title` helper, deliberately duplicated from recommendations | Same strip. Because the helper is deliberately duplicated, apply it in both places or extract one shared helper |
| Library lists | `src/cyo_adventure/api/library.py:284`, `:401` | `GET /api/v1/library` and `GET /api/v1/storybooks/{id}/versions/{version}` | Same strip on any title field. The version fetch returns the raw blob and must **not** strip: that is the artifact the client resolves against |
| Moderation and rescreen re-reads | `src/cyo_adventure/moderation/rescreen.py`, `moderation/classifiers.py` | Re-run classifiers over stored prose | Strip before classification (see 3.3) |
| Pipeline event log | `src/cyo_adventure/events/writer.py:17-19` and the `_PAYLOAD_ALLOWLIST` below it | Per-event-type key allowlist enforcing the PII-free payload contract | Add event types for consent grant, consent revoke, and toggle flip, each with a keys-only allowlist entry (`slot_type`, `ring`, `action`, and at ring 2 `connected_family_id`). **No values, ever.** The allowlist mechanism already prevents this if the new entries are written correctly |
| Notification payloads | `src/cyo_adventure/api/notifications.py:121-133` | Serializes `title` and `body` free text on a guardian-only feed gated before any query runs (`:104-116`) | Strip sentinels. Guardian-only, so the risk is cosmetic rather than a boundary crossing, but an unresolved token in a notification is a visible defect |
| Admin review surfaces | `frontend/src/admin/ReviewDetailPage.tsx`, `ReviewCompare.tsx` | Render node bodies via `PassageText` | Deliberately **do not** strip and **do not** resolve. A reviewer should see which words a family can replace (ADR-023 section 10) |
| Text-to-speech | `frontend/src/reader/useReadAloud.ts:34-99` | Uses the browser `window.speechSynthesis` API on already-substituted text | Not a server guard. Record in the privacy model that on platforms with cloud-backed voices, a personalized passage read aloud may leave the device through a path the app does not control. Surface it in the guardian consent copy |
| Save-state export and sync | `frontend/src/player/types.ts:71` (`ReadingState`) | Carries node ids and variable state only | **Already safe.** No change; add a regression test so it stays that way |
| Ring-3 aggregates | Unbuilt (ADR-016, "Technical Debt") | N/A | Forward-binding constraint: when ring-3 aggregation is built, it must render fully generic. Land this as a test in that workstream, not only as a sentence in ADR-023 |

Implementation note: prefer **one shared strip helper** applied at the serialization boundary over
per-call-site strips. A per-call-site approach is exactly the pattern that gets forgotten on the
29th router.

## 5. P4: data model

Two of ADR-023's included slots already have a home (`child_profile.display_name` for the
protagonist name, and a sibling reference is just another `child_profile.id`). **Everything else
is new collection** and needs a real schema, write-time validation, an erasure path, and an export
entry. That is what this section specifies.

Migrations are Supabase CLI SQL under `supabase/migrations/` (ADR-012), not Alembic.

### 5.1 `child_profile_personalization`: the slot-value store

One row per (profile, slot type), rather than a wide column set, because the taxonomy is expected
to grow and because a per-row grain makes per-slot consent and per-slot erasure natural.

| Column | Type | Notes |
|---|---|---|
| `child_profile_id` | UUID, FK -> `child_profile`, `ondelete="CASCADE"` | Part of the composite PK |
| `slot_type` | `String(32)` | Part of the composite PK; closed vocabulary matching ADR-023's include list |
| `value_text` | `Text`, nullable | Used only by free-text slots; today that is the pet name alone |
| `value_enum` | `String(64)`, nullable | Used by closed-enum slots (pet species, kinship label, home type, favourites) |
| `value_profile_id` | UUID, FK -> `child_profile`, `ondelete="CASCADE"`, nullable | Used by the sibling slot; a reference, never a copied name |
| `ring1_enabled` | bool, default `false` | |
| `ring2_enabled` | bool, default `false` | Must be `false` for any slot whose taxonomy ceiling is ring 1 |
| `created_at` / `updated_at` | TIMESTAMPTZ | |

Constraints, all CHECK-enforced in the migration and mirrored on the ORM `__table_args__` (the
repo has a schema-parity test comparing migration-built and ORM-built schemas, noted at
`db/models.py:554-556`, so the two must agree):

- Exactly one of `value_text`, `value_enum`, `value_profile_id` is non-null.
- `ring2_enabled` is false unless `slot_type` is in the ring-2-eligible set. Per ADR-023's settled
  taxonomy that set is: protagonist name, sibling reference, pet species, pet name, kinship label,
  favourites, home type. The two exclusions are **pronouns** (held back on outing risk) and the
  **dedication line** (addressed to its own household by nature). Encoding the ceiling as a DB
  CHECK rather than only as API validation is what makes ADR-023's ring ceilings structural rather
  than advisory.
- The composite PK `(child_profile_id, slot_type)` gives at-most-one value per slot per profile,
  the same shape `StorybookAssignment` uses (`db/models.py:830-849`).

The protagonist-name pair `real_name_ring1_enabled` / `real_name_ring2_enabled` lives on
`child_profile` itself as two booleans defaulting to `false`, alongside the existing guardian
boolean controls (`tts_enabled:445`, `reduce_motion:449`), because its value is already a column on
that table and inventing a personalization row that points back at `display_name` would be
indirection for its own sake.

Per-skeleton and per-story flags:

- On the storybook version (or the generation job, whichever is cheaper to query alongside the
  blob): `personalization_eligible: bool`, `pronoun_parameterized: bool` (a **separate** flag per
  ADR-023 section 5, off by default, set only by an explicit per-skeleton audit), and the declared
  **sentinel manifest**, so the P2 check has something authoritative to compare against at rescreen
  time without re-reading the contract from disk.

### 5.2 Write-time validation

`api/profiles.py` is already the sole writer for the loosely-typed JSONB column on this table, a
discipline documented at `db/models.py:425-433`. Follow it exactly: one API-layer writer, no other
path.

Every value passes, at write time:

1. `validator/slots.py::structural_value_violations` (`slots.py:496-514`), the public wrapper that
   exists precisely so a caller outside the slot gate can reuse the identical structural-injection
   block. This covers non-emptiness, single-line/control characters, the charset and length rules,
   and the untrusted-input fence-marker guard.
2. `validator/slots.py::denylisted_bundles` (`:282-310`) against
   `band_mandatory_bundles(profile.age_band)` (`:229-240`), which is the band-mandatory floor
   contract data cannot shrink.
3. For enum slots, membership in the shipped closed vocabulary. For the sibling slot, that
   `value_profile_id` names a profile in the **same family** (reusing `authorize_family`,
   `api/deps.py:743-754`).

`display_name` gets the same two checks. It is currently length-bounded free text only
(`api/schemas.py:1032-1034`, written straight to the row at `api/profiles.py:102-103` and `:286`),
which is fine for a label and not fine for something rendered into story prose. Apply the checks
**both** when the guardian sets the name **and** again at payload-build time, because names set
before this feature shipped were never checked. See risk R4.

### 5.3 Ring-2 disclosure consent

A separate table, because consent is per profile **and** per connection, and it enumerates the slot
types it covers (ADR-023 section 3, "the ring-2 consent rule, stated once"):

| Column | Type | Notes |
|---|---|---|
| `id` | UUID, surrogate PK | `UUIDPrimaryKeyMixin`, matching `FamilyConnection` and `ChildProfile`. Needed because the natural key is nullable after tombstoning (below) |
| `child_profile_id` | UUID, FK -> `child_profile`, `ondelete="CASCADE"` | |
| `family_connection_id` | UUID, FK -> `family_connection`, `ondelete="SET NULL"`, nullable | See the tombstone discussion below |
| `connected_family_label` | `String(200)`, nullable | Denormalized at signing time so the record stays legible after the connection row is gone |
| `covered_slot_types` | JSONB array of `slot_type` | The scope of this disclosure |
| `sibling_authority_attested` | bool, default `false` | Set only for a consent covering a sibling name; see 10.1 |
| `consent_accepted_at` | TIMESTAMPTZ | |
| `consent_policy_version` | `String(32)` | |
| `consent_signer_name` | `String(200)` | |
| `consent_ip` | `String(64)` | |
| `revoked_at` | TIMESTAMPTZ, nullable | Explicit revocation, distinct from deletion |

**PK choice, stated because this repo has both patterns.** Use a **surrogate UUID PK plus a partial
unique index** on `(child_profile_id, family_connection_id) WHERE family_connection_id IS NOT NULL`,
not a composite PK. `StorybookAssignment` uses a composite PK (`db/models.py:830-849`) and
`FamilyConnection` uses a surrogate plus `UniqueConstraint` (`:501`, `:543-545`); this table follows
the latter, because tombstoning nulls half of what would otherwise be the composite key.

Mirror the CHECK-enforced pairing already used on `User` (`db/models.py:305-308`: the four consent
columns are all-null or all-populated together). That pairing is what makes the record evidentiary
rather than decorative; copy it exactly.

Re-consent **supersedes in place** on the same row, with a new timestamp and policy version.
Narrowing `covered_slot_types` does **not** require re-signing, because it only shrinks the
disclosure; the row keeps its original signature and the narrowed set. Note the consequence
honestly: after a narrowing, the stored record is a signed superset with a subsequently reduced
scope, so the audit answer to "what did they authorize" is the signature plus the current set, and
the two can differ. If counsel wants the signed set to be immutable, narrowing has to append a new
row rather than update, which is a different design. **Resolved 2026-07-25 (owner choice,
ADR-023 OD-5(c)): narrowing updates in place and does not require re-signing.** The residual noted
above is accepted and belongs in the DPIA rather than in the schema.

#### The connection cascade would destroy the evidence, so it must not cascade

An earlier draft had `family_connection_id` CASCADE on delete, reasoning that "consent cannot
outlive the edge it was granted on". That is backwards for an **evidentiary** record, and it
contradicted this plan's own 5.6, which says retention should follow the consent-evidence
rationale. Connections are deliberately **hard-deleted**, not soft-deactivated
(`api/family_connections.py:6-8`), so a CASCADE would erase the proof of authorization at exactly
the moment disputes arise: after a relationship ends. GDPR Article 7(1) puts the burden on the
controller to *demonstrate* consent was given, and COPPA 312.5 expects retrievable proof of
verifiable parental consent. A record that self-destructs on revocation cannot do either.

Use the pattern this project has already built for exactly this problem. The Article 17(3)
balancing test for `pipeline_event` (`docs/compliance/coppa-gdpr-remediation-plan.md:389-455`) is
the template: retain a **scrubbed evidentiary tombstone** justified under 17(3)(b) and (e),
proportionate because the retained payload carries no content.

Concretely, on connection deletion: `family_connection_id` goes NULL, `revoked_at` is stamped, and
the row survives carrying only *that authorization happened and what it covered*. It never carried
a slot **value** in the first place, which is what makes the tombstone proportionate: the evidence
is the signature, the timestamp, the policy version, and the covered slot-type names, never the
child's actual pet name or sibling. Two consequences: the values themselves live only in
`child_profile_personalization`, which does still CASCADE on profile deletion, so an erasure request
removes every actual detail while leaving the authorization record; and the tombstone must be added
to the Article 17(3) justification in the remediation plan alongside `pipeline_event`, not
justified ad hoc here. P11 carries that.

### 5.4 Deletion cascade: what is automatic and what is new work

The established pattern is `ForeignKey(_FK_CHILD_PROFILE, ondelete="CASCADE")` and
`ForeignKey(_FK_FAMILY, ondelete="CASCADE")`, applied across `ReadingState` (`:747-755`),
`Completion` (`:784-788`), `Rating` (`:811-818`), and `StorybookAssignment` (`:851-858`), each
carrying a `#CRITICAL: data-integrity: CASCADE (Phase 3a, GDPR/COPPA erasure)` marker.

Both new tables FK to `child_profile` with `ondelete="CASCADE"`, so **profile deletion and family
deletion sweep every stored slot value automatically**. No new cascade machinery is needed for the
values.

The one deliberate exception is the consent table's `family_connection_id`, which is `SET NULL`
rather than `CASCADE` (5.3): connection deletion leaves an evidentiary tombstone, profile deletion
still removes the whole row. Note the ordering that makes this coherent: erasure of the **child**
removes the consent record entirely, because the data subject is gone; deletion of the
**connection** keeps it, because the data subject still exists and may later dispute what was
authorized.

What **is** new work: `tests/integration/test_deletion_drill.py` asserts erasure table by table,
explicitly (see `test_delete_profile_removes_child_linked_rows` at `:115` and
`test_delete_my_family_removes_everything` at `:208`). Both tests must gain seed rows and
assertions for the two new tables, or the cascade is untested and the drill silently under-claims.
Add one more case the drill does not currently have a shape for: deleting a **connection** leaves
the tombstone, and deleting the **profile** then removes it.

### 5.5 Export

`me.py::_assemble_family_export` (`:93-175`) is **hand-assembled table by table**, not reflective:
it explicitly selects `ReadingState`, `Completion`, `Rating`, `StorybookAssignment`, and story
requests, and builds a dict per row. New tables are therefore **not** picked up automatically.

`GET /api/v1/me/export` (`me.py:235`) must be extended to return, per profile:

- Every `child_profile_personalization` row: `slot_type`, the populated value, both ring flags,
  and timestamps. Return the sibling slot as the referenced profile's id **and** display name, so
  the export is human-readable rather than a UUID the guardian cannot interpret.
- The two ring toggles that live on `child_profile` itself, `real_name_ring1_enabled` and
  `real_name_ring2_enabled`. Easy to miss because they are not in the new table, and omitting them
  would make the export claim a narrower disclosure posture than the account actually holds.
- Every ring-2 consent row, **including tombstoned ones** (`family_connection_id IS NULL`): the
  `connected_family_label`, `covered_slot_types`, `sibling_authority_attested`, the four consent
  columns, and `revoked_at`. A guardian asking "who did I share what with, and is it still on"
  should be answerable from the export alone, including for relationships that have since ended.

### 5.6 Privacy-model classification

`docs/planning/privacy-model.md` has a "Data Classification" section (`:36`) and an "If Shared
Beyond Family" section (`:278`). Both need entries. Do not settle for a generic privacy-notice
bullet:

- **`child_profile_personalization`**: child-linked data, **same tier as `child_profile` fields**.
  Guardian-supplied, never sent to a provider, never persisted into story content, delivered to
  family devices as a values payload. Retention: life of the profile, purged by the existing
  profile-deactivation grace window in the retention table
  (`docs/compliance/coppa-gdpr-remediation-plan.md:712`).
- **Ring-2 disclosure consent**: consent evidence, same tier as the `User` consent columns.
  Retention should follow the consent-evidence rationale, not the reading-data rationale; flag for
  the same counsel pass as ADR-018 D1.
- **The client-held values payload**: child-linked data at rest on a device, in the same category
  as the offline `reading_states` store already covered by the SEC-F5 sign-out purge
  (`frontend/src/offline/db.ts:192-201`).
- **The "If Shared Beyond Family" section** gains the ring-2 flow explicitly: which slot types can
  cross, under which consent, and the prospective-not-retroactive revocation limit.

## 6. P5: API surface and contract regeneration

New routes, all under the existing `/api/v1` prefix:

| Route | Caller | Purpose |
|---|---|---|
| `GET /api/v1/profiles/{profile_id}/personalization` | Guardian | Read a profile's slot values and ring flags for the settings UI |
| `PUT /api/v1/profiles/{profile_id}/personalization` | Guardian | Write slot values and ring flags; the sole writer, validated per 5.2 |
| `GET /api/v1/storybooks/{storybook_id}/personalization-values` | Reader session (child, device, or guardian) | The values payload for **whichever ring applies**, resolved server-side from the book's subject and the caller's family. One route for both rings; see 8.3 for why the client must not name the connection |
| `POST /api/v1/profiles/{profile_id}/ring2-consent` | Guardian in the **sharer** family | Grant or supersede a ring-2 disclosure consent for a specific connection and slot-type set |
| `DELETE /api/v1/profiles/{profile_id}/ring2-consent/{connection_id}` | Guardian in the sharer family | Revoke it |

Two routing notes:

- The values route deliberately returns the payload **separately from the story**, never embedded
  in `GET /api/v1/storybooks/{id}/versions/{version}` (`library.py:401`). That separation is what
  keeps the story response byte-identical for every viewer and the `id@version` cache key valid.
- The ring-2 consent routes are gated to the **sharer-side** guardian. Note that
  `FamilyConnection` is directional with `family_id` as the *viewer* and `connected_family_id` as
  the *sharer* (`db/models.py:501-507`), which is the opposite of the intuitive reading; get the
  direction right or the consent will be collected from the wrong household.

### 6.1 Request and response shapes

Route table entries are not schemas. Four shapes need pinning before P5 can be written, and one of
them resolves a question the predicate in 8.4 implicitly raised.

**`PUT /api/v1/profiles/{profile_id}/personalization`** takes the whole personalization state for
one profile, as a replace-not-patch body, because a partial patch over a per-slot table invites
ambiguity about whether an absent key means "unchanged" or "cleared":

```text
{
  real_name_ring1_enabled: bool,
  real_name_ring2_enabled: bool,
  slots: [
    { slot_type: str, value_text?: str, value_enum?: str,
      value_profile_id?: uuid, ring1_enabled: bool, ring2_enabled: bool }
  ]
}
```

**The two `real_name_*` booleans are written through this route, not the existing profile-update
route**, even though they live on `child_profile` rather than the new table. The reasoning: they are
personalization state semantically, and splitting one guardian screen's save across
`PATCH /profiles/{id}` (`api/profiles.py:315`) and this route would make a partial failure leave a
profile half-configured, with the name enabled and the slot rows not. One route, one transaction.
`ProfileUpdateBody` gains nothing.

**`GET /api/v1/profiles/{profile_id}/personalization`** returns the same shape plus, per slot, a
read-only `ring2_eligible` derived from the taxonomy ceiling, so the UI can grey out what the DB
CHECK would reject anyway rather than reimplementing the ceiling list in TypeScript.

**`POST /api/v1/profiles/{profile_id}/ring2-consent`**:

```text
{
  family_connection_id: uuid,
  covered_slot_types: [str],
  policy_version: str,
  signer_name: str,
  accepted: true,
  sibling_authority_attested?: bool   // required true when covered_slot_types includes the sibling slot
}
```

`consent_ip` and `consent_accepted_at` are stamped server-side, never accepted from the client,
mirroring how `POST /v1/onboarding` handles the ADR-018 D1 consent.

**`GET /api/v1/storybooks/{storybook_id}/personalization-values`** takes **no** requested-slot-type
parameter. An earlier draft's predicate said "for each requested slot type", implying one; there
should not be. The server returns every slot type the subject has enabled and consented for at the
applicable ring, filtered by 8.4. Letting the client request a subset would add a parameter that
can only ever narrow a result the server already computed, while giving an attacker a probe
dimension. The client discards what it does not need.

Response (both rings, identical shape):

```text
{ subject_profile_id: uuid, ring: 1 | 2, policy_version: str,
  resolved_at: timestamp, values: { <slot_type>: str } }
```

An empty `values` object is the universal failure mode, per 8.4.

### 6.2 OpenAPI contract regeneration (do not skip)

This repo's frontend has no hand-written request/response types; the axios client under
`frontend/src/client/` is generated from the backend OpenAPI schema and **committed to git**. CI
enforces it: the `contract` job in `.github/workflows/ci.yml:432` dumps the schema in-process
(`:477`), regenerates the client (`:497`), and fails the build on any diff
(`:501`, "Generated OpenAPI client is out of date").

So every backend route or Pydantic model change above requires, in the same commit:

```bash
cd frontend && npm run generate-client   # against a live backend, per frontend/README.md
git add frontend/src/client
```

This is an explicit step in P5, not a cleanup afterwards. A P5 PR that adds routes without the
regenerated client will fail CI.

## 7. P6: client-side resolution (ring 1)

### 7.1 Where it lives

`frontend/src/player/`, next to the existing engine (`engine.ts`, `evaluator.ts`, `machine.ts`,
`series.ts`, `types.ts`). That directory already exists to mirror backend logic on the client and
already carries the test discipline this needs. A new `personalization.ts` plus
`personalization.test.ts` fits the established shape.

The resolver is a pure function: `(text: string, values: ValuesPayload | null) => string`. Given
`null` or a missing key it returns the generic default. It must be pure, total, and synchronous, so
it can be called from render without a loading state and so a missing payload degrades to the
generic experience rather than to an error.

### 7.2 Where it is applied

`frontend/src/reader/Reader.tsx` renders node bodies through
`<PassageText text={node?.body ?? ''} />` (`Reader.tsx:365`, `:419`) and passes body plus choice
labels to read-aloud (`:96`, `:151`). Substitution is applied at those render sites, and to choice
labels and ending titles, and nowhere else.

Deliberately **not** substituted: the admin review surfaces, which use the same `PassageText`
component (`frontend/src/admin/ReviewDetailPage.tsx`, `ReviewCompare.tsx`). An admin reviews the
generic artifact, which is the artifact that was approved and stored. See ADR-023 section 10.

### 7.3 The values payload

```text
{
  subject_profile_id: string,
  ring: 1 | 2,
  policy_version: string,
  resolved_at: timestamp,
  values: { <slot_type>: string }
}
```

Rules:

- Fetched per profile, **never embedded in a story response**.
- Small and bounded: at most one short string per included taxonomy entry.
- Stored in its own IndexedDB store keyed by `subject_profile_id`, so a single-key delete revokes
  it. Do **not** put it in the `storybooks` store, which is deliberately device-wide and
  profile-independent (`frontend/src/offline/db.ts:17-21`).
- Server-side validated at build time per 5.2; the client falls back to the generic default rather
  than rendering anything malformed that arrives anyway.

### 7.4 Offline and revocation mechanics

- **The story cache is untouched.** `cacheStorybook` keys by `` `${story.id}@${story.version}` ``
  (`frontend/src/offline/db.ts:161-163`). Because the blob is identical for every reader, this
  stays correct and siblings keep sharing one entry. This is the payoff of the whole architecture;
  do not undo it by adding a profile dimension to that key.
- **A new store** for values payloads, added as a `DB_VERSION` bump in the `upgrade` callback
  (`db.ts:92-116`), following the existing `if (oldVersion < N)` pattern. The existing
  `blocking` / `blocked` / `terminated` handling (`db.ts:117-136`) exists because a version bump
  can hang every tab; a bump is not free and should carry its own test, as the current ones do.
- **Purge triggers.** Delete the values payload on: any ring flag flipping to off, ring-2 consent
  revocation, ring-2 connection revocation, profile deactivation, guardian sign-out and device
  handover (alongside the existing `clearReadingStates`, `db.ts:198-201`), and consent
  policy-version change. Add these to `frontend/src/offline/revocation.ts` next to
  `reconcileOfflineCache` (`:85`), but keep them **separate** from it: that function's `#CRITICAL`
  contract is that it runs only after a successful authoritative library fetch (`:39-52`), and a
  values purge has different, looser preconditions. Do not overload it.
- **The honest limit.** A device offline at the moment of revocation keeps its payload until it
  next opens the app and completes a fetch. `revocation.ts:16-25` already documents an analogous
  mid-read gap for book revocation. Document this one the same way, in code, and make sure the
  guardian-facing copy says "new readings" rather than implying retroactive erasure.

### 7.5 The feature flag

P6 through P8 ship behind `VITE_FEATURE_PERSONALIZATION`, a build-time Vite env flag read once and
threaded through a single `isPersonalizationEnabled()` helper, matching how the rest of the
frontend reads `VITE_`-prefixed config. Off means: no values fetch, no resolver call, no settings
UI, and the reader renders generic. The backend routes may exist while the flag is off; the
server-side artifact is generic either way, so a half-deployed state is safe by construction.

## 8. P7: ring-2 cross-family delivery

This is the section the design was missing. "Ring 2 is allowed" is a policy; this is the mechanism.

### 8.1 The product situation, concretely

Two families, connected. The Ruiz family (Alex, age 9) and the Diaz family (Mateo, age 8). The
guardians have an active `family_connection`.

**Before this feature.** A book generated for Alex is published. If its `visibility` is `catalog`,
Mateo's guardian can assign it to Mateo, and Mateo reads it. Every reader, in both households, sees
the generic protagonist ("Explorer"). Separately, Alex's 5-star rating on that book surfaces in
Mateo's recommendation feed with "Alex" as `recommender_name`, which is the ring-2 attribution
disclosure PR #415's B6 already sanctioned.

**After this feature, with everything opted in.** Alex's guardian enables
`real_name_ring2_enabled` on Alex's profile and signs a ring-2 disclosure consent naming the Ruiz
to Diaz connection and the slot types it covers. Now when Mateo opens that same book, Mateo's
reader recognises that the book's personalization subject is a profile outside the Diaz family,
fetches Alex's ring-2 values, and renders "Alex" where the sentinel sits. Mateo is reading a story
about his cousin Alex, by name. The stored blob is still generic and still byte-identical to what
every other family in the catalog receives.

**With anything not opted in.** Consent missing, ring-2 flag off, connection revoked, or the
reading family simply unconnected: the values fetch returns empty and the reader renders
"Explorer". No other enforcement is required anywhere.

### 8.2 The personalization subject

The mechanism needs to know *whose* values a given book resolves against. Today a `Storybook`
carries `family_id` (`db/models.py:640`) and a `StoryRequest` carries a nullable `profile_id`
(`db/models.py:903-921`), which is set to NULL when the profile is deleted (asserted at
`tests/integration/test_deletion_drill.py:183`). That nullable link is too weak to authorize on.

Add an explicit `personalization_subject_profile_id` on the storybook, nullable, FK to
`child_profile` with `ondelete="SET NULL"`. Set at generation time from the requesting profile.
`SET NULL` rather than `CASCADE` is deliberate here and is the one place this feature deviates from
the table-wide CASCADE pattern: deleting Alex's profile must not delete a book the Diaz family has
on their shelf, but it must sever the personalization link so the book reverts to generic
everywhere. That severing is the erasure mechanism described in 8.5.

### 8.3 Discovery: the client cannot name what it cannot see

An earlier draft of this section specified a route taking `connection_id` and `profile_id`, without
checking whether the reading client can obtain either. It cannot, and both halves fail:

- **`connection_id` is unreachable from a child session.** Every connection-listing and consent
  route is guardian-gated: `_require_guardian` (`api/family_connections.py:241-256`) is called
  first thing in `list_my_family_connections` (`:371`), `get_family_connection_consent` (`:406`),
  `consent_family_connection`, and `revoke_family_connection_consent` (`:461`). A `Role.CHILD`
  principal gets a 403 from all of them, correctly. There is no child-readable connection list and
  there should not be one.
- **`personalization_subject_profile_id` is in no response shape.** Nothing the client can read
  tells it whose values a book resolves against.

The naive fix, surfacing the subject profile id on the book, is worse than the problem: a
catalog-visible book is readable by **every** family, so putting a foreign `child_profile` UUID on
it would leak the existence and identity of a subject to unconnected households, which is precisely
the ring-3 boundary this design exists to hold.

**Resolution: the server resolves the connection; the client never names it.** The route drops
`connection_id` entirely and is keyed on the book:

`GET /api/v1/storybooks/{storybook_id}/personalization-values`

The server derives everything from the caller's own principal and the book:

1. Load the book, read its `personalization_subject_profile_id`.
2. If the subject is in the **caller's own family**, this is the ring-1 path: apply the ring-1
   gate and return.
3. If the subject is in **another** family, look up a `FamilyConnection` where
   `family_id == principal.family_id` and `connected_family_id == subject.family_id`. If none
   exists, return an empty payload.
4. Apply the ring-2 predicate in 8.4 against that resolved connection.

This is strictly better on three counts. The client needs no knowledge it is not entitled to. One
route serves both rings, so the reader has one call site and no branching on a fact it cannot
determine. And an unconnected family calling it on a catalog book gets an empty payload that is
indistinguishable from "this book has no personalization at all", so the route leaks nothing about
whether a subject exists.

The client's only new knowledge is a boolean already safe to publish: `personalization_eligible`
on the library and version responses, which says "this book contains sentinels" and nothing about
whose. The reader calls the values route only when that boolean is true, purely to avoid a pointless
request.

### 8.4 The endpoint and its authorization predicate

`GET /api/v1/storybooks/{storybook_id}/personalization-values`

Returns a values payload, or an **empty payload** (not a 403) when any condition fails. Empty
rather than an error is deliberate: a 403 distinguishes "consent exists but you cannot have it"
from "no consent exists", which leaks the existence of a consent relationship. An empty payload
renders generic and tells the caller nothing.

The predicate, all of which must hold:

1. **The caller is authenticated and belongs to the viewer family.** `principal.family_id` equals
   `connection.family_id`. Recall the direction: `family_id` is the viewer, `connected_family_id`
   is the sharer (`db/models.py:501-507`).
2. **The connection is active.** Both `consented_by_viewer_user_id` and
   `consented_by_sharer_user_id` are non-null. Reuse the existing `_is_dual_consented` shape from
   `api/recommendations.py:178-196`, which deliberately applies the check as an explicit Python
   boolean per row rather than as a SQL `WHERE` clause "a future edit could silently loosen"
   (`recommendations.py:214-221`). Follow that convention exactly; it is the house style for this
   check and it exists for a reason.
3. **The subject profile belongs to the sharer family.** `profile.family_id` equals
   `connection.connected_family_id`. Without this, a connection to one family would authorize
   reading values from any profile whose id you could guess.
4. **The subject profile is live.** `deactivated_at` **and** `processing_restricted_at` are both
   NULL (`db/models.py:486`, `:498`). These are not decorative. `deactivated_at` is the
   soft-remove that already excludes a profile from every picker listing and refuses a new child
   session (`:480-486`); continuing to broadcast a deactivated child's name into another household
   would contradict that directly. `processing_restricted_at` is the GDPR Article 18
   restriction-of-processing state, described in its own comment as "keep the data, stop actively
   processing it" (`:487-497`); a cross-family disclosure is unambiguously active processing, and
   it is a broader one than the new-story-request block Article 18 currently gates. Omitting these
   two checks would have made this endpoint the one place a restricted profile's data still flowed
   outward.
5. **The subject profile's ring-2 flag is on** for each slot type in the requested set
   (`real_name_ring2_enabled`, or `ring2_enabled` on the personalization row).
6. **A ring-2 disclosure consent row exists** for `(profile_id, connection_id)` and its
   `covered_slot_types` includes the slot type. Slot types passing 5 but not 6 are omitted from the
   payload individually; the payload is filtered, not all-or-nothing.
7. **The slot type's taxonomy ceiling is ring 2.** Belt and braces behind the DB CHECK from 5.1, so
   a pronoun or a dedication can never be returned here even if a row were somehow flagged.
8. **For the sibling slot only: the referenced child is separately cleared.** An earlier draft said
   "conditions 4 and 5 are additionally evaluated against `value_profile_id`", which was ambiguous
   in a way that mattered. Read literally it is incoherent: re-evaluating the *sibling-reference*
   slot type against B would consult B's own sibling row, which points at somebody else entirely.
   The intended reading, now pinned:

   > When resolving A's sibling slot, which holds B's name, the server evaluates conditions 3, 4,
   > 5, 6 and 7 against **profile B** for the **protagonist-name slot type**, on this same
   > connection. B's name is disclosed under B's own name-sharing settings and B's own consent
   > record, never under A's.

   Concretely: B must be in the sharer family, live and unrestricted, have
   `real_name_ring2_enabled` true, and have a ring-2 consent row for this connection whose
   `covered_slot_types` includes the protagonist name. If any fails, A's sibling slot alone is
   omitted and the rest of A's payload is unaffected.

   **This stretches the consent, and the consent copy must stretch with it.** B's guardian signed a
   consent whose natural reading is "B's name may appear in B's shared stories." Using it to
   authorize B's name appearing as a companion in *A's* book is a different context, and reading it
   that way silently would be exactly the kind of scope creep a signed disclosure consent is
   supposed to prevent. So this predicate is only defensible if the ceremony copy says so: the
   ring-2 name consent must be worded to cover **"this child's name appearing in any of this
   family's stories shared with the connected family"**, not only stories where they are the
   protagonist. Section 10.1 carries that wording requirement. **Confirmed as adequate 2026-07-25
   (owner choice, ADR-023 OD-5(b)): no separate, narrower consent event is required for a companion
   appearance**, provided the ceremony wording covers it explicitly. Still flagged for counsel
   alongside the rest of OD-5.

   Note the useful consequence for revocation: turning B's ring-2 name sharing off silently
   degrades A's book to the generic companion name on the next fetch in the connected household,
   with no action needed on A's profile.

### 8.5 Who actually calls it

This is the part that needs care, because the intuitive answer is wrong.

A **child session** (`Role.CHILD`) is profile-scoped: `Principal.profile_ids` lists only the
profiles it may act on, and `authorize_profile` (`api/deps.py:721-733`) rejects anything outside
that set. A **device** principal is even narrower: `profile_ids` is force-cleared in
`__post_init__` because "a device grant authorizes a child-session mint and a profile listing, not
any per-profile read/write" (`api/deps.py:160-163`). Neither can, or should, be handed a general
"read another family's profile data" capability.

The resolution: **the endpoint does not authorize on the subject profile at all.** It authorizes on
the *connection*, which is a family-level fact, plus the caller's family membership. A child
session in the Diaz family passes condition 1 because `Principal.family_id` is set for every
principal including children, and it never needs `authorize_profile` against Alex's profile,
because it is not acting on Alex's profile: it is reading a payload the Ruiz guardians published
to that connection.

That is a genuinely new authorization shape for this codebase, which is exactly why it needs
stating. Every other cross-family gate here is `authorize_family` (`api/deps.py:743-754`), which
compares `principal.family_id` to a resource's owner and rejects on mismatch. This endpoint
deliberately permits a mismatch, under a named, revocable, dual-consented edge. It should therefore
get its own helper (`authorize_via_connection`) rather than reusing or loosening
`authorize_family`, and its own row in `tests/integration/test_authz_matrix.py`'s `ROUTE_TABLE`,
which is where the repo pins per-route principal expectations.

Enumeration note: after the 8.3 reshaping, the only client-supplied identifier is
`storybook_id`, which the caller already had to possess to open the book. There are no
connection or profile ids to probe, and every failure mode returns the same empty payload, so the
route reveals nothing about whether a subject or a connection exists. It should still be counted
against the caller's rate budget like any other.

### 8.6 Does the receiving family need their own consent or notice?

Evaluated rather than assumed, because the predicate in 8.4 is entirely sharer-side: every
condition protects Alex's household, and nothing anywhere asks the Diaz guardians whether they want
their children reading another family's child's real details.

**The case that they need one.** The Diaz guardians consented to a `family_connection` whose entire
documented purpose is recommendations: ADR-016 scopes ring 2 to "book reference, recommender
display name, and rating/like", and the ORM docstring calls it "a directional cross-family opt-in
for story recommendations" (`db/models.py:502`). Reading Alex's real first name, pet's name and
sibling's name woven through a book their eight-year-old reads is not a recommendation. Stretching
the viewer-side consent to cover it is the mirror image of the sibling-consent stretch this plan
already refuses to make silently in 8.4 condition 8. Consistency alone argues for a gate.

**The case that they do not.** The receiving family incurs no privacy risk of their own; they are
the recipients, not the subjects. Consent doctrine protects data subjects, and the Diaz children
are not the subject here. A consent gate on the receiving side is really a *content preference*,
not a consent, and dressing it as consent muddles both.

**Conclusion: a viewer-side notice and control, deliberately not framed as consent.** The receiving
guardian gets (a) a one-time notice the first time a personalized cross-family book appears on one
of their children's shelves, naming the connected family and what kind of details may appear, and
(b) a persistent per-family off switch that makes their household render everything generic
regardless of what the sharer enabled. No signature, no policy version, no evidentiary record: it
is a preference, stored alongside their other family settings.

Two reasons this is the right shape rather than a full consent ceremony. It respects the actual
asymmetry, since the sharer bears the privacy risk and signs, while the viewer bears only an
editorial one and merely chooses. And it closes the real gap, which is not legal exposure but the
plain surprise of a guardian discovering their child is reading a book naming a real cousin without
anyone having told them. A notice fixes surprise; a signature would not fix it any better.

Implementation: one boolean on `Family` (default on, since the connection consent already implies
willingness to receive from this household), one predicate condition evaluated viewer-side, and a
dismissible first-encounter notice in the reader. Add it as condition 0 in 8.4's list when
implementing, evaluated before any sharer-side lookup, so a household that has opted out never even
causes a subject resolution.

### 8.7 Cross-family erasure propagation

When the Ruiz family deletes Alex's profile (an ADR-018 erasure event, `DELETE /api/v1/profiles/{id}`),
here is what happens to Alex's name already sitting on a Diaz device.

**Server-side, immediately and completely.** The profile row is deleted;
`child_profile_personalization` and the ring-2 consent rows CASCADE (5.4);
`storybook.personalization_subject_profile_id` goes NULL (8.2). The next values fetch from any Diaz
device returns empty, because condition 3 cannot be satisfied by a profile that no longer exists.
Every future render, in both households, is generic.

**Client-side on the Diaz device, prospectively.** A payload already in that device's IndexedDB
survives until that device next opens the app and completes a fetch, at which point the empty
response clears it. This is the same prospective-not-retroactive limit ADR-023 states for ordinary
revocation, and it applies with more force here because the device belongs to a different
household that this system cannot reach out and purge.

Two things worth saying plainly rather than glossing:

- The severed link **is** a real signal. Because the values fetch is per-render and per-connection,
  the connected family's very next online read reflects the erasure. This is materially better than
  a design where the name was baked into the blob, where erasure would require re-issuing content
  the other household has already downloaded.
- It is still **not** a retroactive claw-back, and an erasure response to a guardian must not claim
  it is. The accurate statement is: "we have deleted it everywhere we control, and connected
  families' devices revert the next time they connect." Draft that sentence into the erasure
  response template in Phase 3 of the remediation plan rather than improvising it under a
  one-month Article 12(3) clock.

### 8.8 Tests this phase must carry

- Each of the eight predicate conditions, failing independently, returns an empty payload (or, for
  condition 8, a payload with the sibling slot omitted and everything else intact).
- A revoked connection consent (either side) empties the payload on the next call, using the
  existing `DELETE /api/v1/family-connections/{id}/consent` route
  (`api/family_connections.py:437`).
- A subject profile with `deactivated_at` set, and separately one with `processing_restricted_at`
  set, each return an empty payload while every other condition holds.
- A pronoun or dedication slot type is never returned across a ring-2 resolution, even with a
  hand-forged row that has `ring2_enabled` set.
- The sibling case, all four combinations: A opted in and B opted in returns the name; A opted in
  and B not omits the sibling slot only; B opted in and A not returns nothing; neither returns
  nothing. Plus: B deactivated or restricted omits the sibling slot only.
- A child session in the viewer family succeeds; a child session in an unrelated family, and a
  device principal, both get empty.
- An unconnected family reading the same catalog book gets a payload indistinguishable from that
  of a book with no personalization at all (8.3's non-disclosure property).
- Profile deletion in the sharer family empties the payload on the next call. Deleting sibling B's
  profile omits the sibling slot from A's payload while leaving A's own name intact.

## 9. P8: the dedication-line overlay

ADR-023 row 8 is the one included slot that does not resolve a sentinel, because there is no
sentinel in the blob for it: a dedication is not story prose. It was reconsidered for deferral on
the theory that it is a separate mechanism; ADR-023's taxonomy note records why that theory does
not hold, and this section is the concrete evidence. **It adds one `slot_type` row, one boolean,
and one component. Nothing else.**

- **No new storage.** Its two parameters already exist: the name is `child_profile.display_name`
  (taxonomy row 1) and the kinship label is a closed enum of exactly the shape row 5 already
  stores. The dedication gets its own `slot_type` in `child_profile_personalization` (5.1) holding
  a kinship label in `value_enum` plus its ring-1 flag, because the "from" kinship (who the book is
  dedicated by) can legitimately differ from the in-story trusted-adult kinship. Same table, same
  columns, same constraints. The composed string is **never stored**.
- **No new validation path.** The name is already checked by 5.2 for row 1; the kinship label is
  enum membership, identical to row 5. Nothing here calls a validator the other slots do not.
- **No new revocation path.** It reads from the same values payload, so every purge trigger in 7.4
  removes it with zero additional code.
- **No new server-side leak surface.** No API serializes it, because there is nothing to
  serialize: the payload carries a kinship enum and a name the payload already carried.
- **What is actually new**: one React component. Render it as a title-page overlay on the reader's
  opening screen, in `frontend/src/reader/` alongside `ReaderChrome.tsx`, composed from the fixed
  template `For {NAME}, love {KINSHIP}`. It is a sibling of the passage, never part of it: it never
  enters `node.body`, never reaches `PassageText`, and never appears in any title field.
- **Ring 1 only**, enforced by the DB CHECK in 5.1 and predicate condition 7 in 8.4. This is not a
  risk judgment; a dedication is addressed to its own household and means nothing in another one.
- **Template is fixed, not guardian-authored.** A free-text dedication would be a new
  unmoderated-prose surface on a kid-facing screen, which is the one thing this whole architecture
  exists to avoid. If the product later wants free-text dedications, that is a separate feature
  with its own moderation path, and it should not borrow this one's justification.

Sequenced **last** among the included slots for exactly the reason it was almost cut: it shares
nothing with the sentinel work, so it can slip a release without blocking anything, and it should
be the first thing dropped if P1 through P7 run long.

## 10. P9: guardian surfaces and the child-facing control

### 10.1 Guardian

- Toggle UI in the guardian profile editor (`frontend/src/guardian/`, alongside existing profile
  management), everything default off, framed per ADR-023 section 8: the fictional-protagonist
  experience is the recommended default, and real-name substitution is an escalation on top of it,
  not a fix for a degraded state.
- Ring-2 consent capture reuses the *shape* of `GuardianConsentPage.tsx` (built for ADR-018 D1) but
  is a **separate flow with separately-worded copy** and a separate record.
- The consent screen must be reached from the **sharer** side (see the direction warning in 6).

#### 10.1.1 What the ring-2 consent ceremony must actually say

Three requirements, each traceable to a specific design decision elsewhere in this plan rather than
to general caution. Draft copy is counsel's to review; these are the constraints on it.

1. **Enumerate the slot types by name, in plain language.** The stored record carries
   `covered_slot_types`, and the whole point of enumerating is that the scope of a past disclosure
   is legible after the fact. A signature over "personalization details" would make the enumeration
   decorative. Name them: "Maya's first name", "her pet's name", "her brother's first name". Also
   state what is **not** covered, since pronouns are permanently ring 1 and a guardian will
   reasonably wonder.
2. **The name clause must cover companion appearances, not just protagonist ones.** Predicate
   condition 8 in 8.4 reads sibling B's own name consent to authorize B appearing as a companion in
   sibling A's book. That is a real stretch of what "B's name may be shared" naturally means, and
   the predicate is only defensible if the copy anticipates it. Required wording, in substance:
   **"[Child]'s first name may appear in any story this family shares with [connected family],
   including stories about their brothers or sisters."** Without this sentence, condition 8 is
   authorizing a disclosure nobody agreed to, and it should be considered blocked.
3. **A separate parental-authority attestation for the sibling case.** This design leans on
   "the same guardian holds parental responsibility for both children", which the system infers
   from two profiles sharing a family account and has never verified or asked about. Taxonomy row 3
   is titled "sibling **or family-child** name" and deliberately admits stepchildren, foster
   placements, and extended-family arrangements where the account-holding adult may not hold legal
   authority over the second child. So when `covered_slot_types` includes the sibling slot, the
   ceremony adds a distinct checked attestation, recorded as `sibling_authority_attested`:
   **"I am the parent or legal guardian of [B], and I have authority to consent to sharing their
   first name."** It is a separate affirmation, not a clause buried in the main one, because it is a
   different claim about a different child. **Confirmed sufficient 2026-07-25 (owner choice,
   ADR-023 OD-5(a)): the attestation is accepted and the sibling slot does not stay ring-1-only
   pending independent verification of authority.** Still flagged for counsel, since an attestation
   is a self-declaration rather than a verification.

The ceremony must also state, as ordinary copy: that revocation is prospective and takes effect on
the connected household's next connection, not instantly; and that the value never reaches any AI
provider and is never stored inside the story itself.

### 10.2 The child-facing control, and what "one-way" actually means

Earlier drafts of this design described a "one-way veto", which was imprecise and read as though a
child could switch personalization off and then be stuck. The real invariant is about the
**guardian-consent boundary**, not about the switch:

> A child may turn substitution off and back on freely, **within the envelope their guardian has
> already consented to**. A child can never enable a slot type, or a ring, that the guardian has
> not enabled. Turning it off never requires an adult; turning it back on never widens the
> disclosure beyond what the guardian already granted.

So the control is an ordinary on/off from the child's point of view, and the one-way property is
the ceiling above it, which the child cannot raise. Concretely: the child's switch multiplies with
the guardian's settings, it never adds to them.

Implementation notes:

- Per profile, per device, persisted locally. It does not change the server-side toggle (a
  guardian's consent is unchanged by a child's local preference) and it needs no network call, so
  it works offline.
- It reads as a preference, not a warning: "Use my name in stories", with an on/off. Not "This book
  contains your personal data."
- **Not rendered at all for the 3-5 band**, and for practical purposes reviewed again for 5-8, per
  ADR-023 section 9. A control a pre-reader cannot exercise is not a safeguard; rendering one
  anyway would misrepresent the protection in a compliance review. For those bands the guardian
  setting is the whole mechanism, and the guardian settings screen should say so in as many words.

## 11. P10: catalog migration

Per ADR-023 section 6: existing catalog content is test and development material with no live
child-linked production data, so there is no backward-compatibility obligation.

- **Replace by default.** Regenerate stories onto the new sentinel-tagged standard. The volume is
  small (61 skeletons, 45 with contracts) and it is test content.
- **Repair only where a specific story is expensive to reproduce.** Repair here means a
  purpose-built reprocessing pass, not `moderation/repair.py::attempt_repair`, which is a narrow
  soft-gate re-prompt that "only produces the candidate revision; it does not decide whether to
  adopt it" (`repair.py:6-7`). Reusing its shape is a deliberate build, not a reuse.
- Any story not migrated is simply `personalization_eligible = false` and renders exactly as it
  does today. There is no forced migration deadline.
- **Pronoun audit is separate and per skeleton.** Gendered pronouns are hardcoded in beats guidance
  and choice labels: `skeletons/10-13/the-cinderwick-exchange.json:89` ("she tells {HERO} the
  escapement is worn"), `skeletons/10-13/the-envoy-of-three-courts.json:135` ("See {COURIER} on his
  way and snatch some sleep"), `:331`, `:582`, `:760`, `:862`. Every node body in the catalog is a
  `<<FILL ...>>` directive, so this is an audit of authoring directives, not of stored prose. A
  skeleton gets `pronoun_parameterized = true` only after someone has read its directives and
  confirmed a pronoun swap produces coherent text.
- **Role-safety audit rides along** (risk R11): while auditing pronouns, mark which slots may carry
  a real person's name and which are antagonist or mishap roles.

## 12. P11: copy, erasure, and compliance artifacts

- **Route A messaging: the copy is drafted, the mechanism is not.** Per ADR-023 OD-3 (decision
  confirmed 2026-07-25), the replacement strings are already written and live in ADR-023's
  coordination section, Ask 1b. This bullet is now about wiring, not wording. Also, while in this
  file, fix the stale "Section 5 Decision 4" citation at `interpretation.py:174`.

  **Correction to a working assumption, because it changes the size of this task.** The change was
  described during review as a free branch, on the basis that "the disposition renderer already has
  access to the requesting child's profile". It does not. `render_interpretation`
  (`interpretation.py:1249-1257`) takes exactly `elements`, `band`, `layer`, `created_at`,
  `skeleton_slug`, `contract_version`, and its docstring pins its purity ("Pure: builds `kid_text` /
  `guardian_text` for every element from the template catalog (never model output) ... `created_at`
  is supplied by the caller so the module reads no wall clock"). The catalog is keyed
  `(disposition, reason, band_group)` (`interpretation.py:706`), with no profile or toggle axis.

  It is still a small change. It is three specific edits:

  1. **Catalog key gains a toggle axis.** Extend the key to
     `(disposition, reason, band_group, personalized: bool)`. `_register` (`:709-721`) takes three
     optional extra `_TemplatePair`s (`young_personalized`, `middle_personalized`,
     `teen_personalized`) that default to the standard ones, so **only** the
     `IDENTITY_PROTECTION` registration supplies them and all ~10 other registrations are
     untouched.
  2. **`render_interpretation` gains one keyword-only parameter**, `name_personalization_enabled:
     bool = False`, forwarded to `_render_pair`. Pass a **bool, not the profile object**: the
     module's purity discipline (stdlib and pydantic only, no ORM, no I/O) is load-bearing and
     handing it a `ChildProfile` would break it for no gain. The default keeps every existing
     caller and the five test call sites in `tests/unit/test_interpretation.py` compiling
     unchanged.
  3. **Five production call sites thread the flag**: `generation/worker.py:380`, `:433`, `:532`,
     and `interpretation.py:1441`, `:1487`. Each of these already resolves the requesting profile
     (or can, in the same query), so each passes `profile.real_name_ring1_enabled`.

  Note the flag is deliberately **ring-1 only**: the disposition message is shown to the requesting
  child in their own family, so ring 2 is irrelevant to which variant they see.

  **Sequencing (ADR-023 OD-3, and repeated from section 1):** this is a **P9 exit criterion**, not
  a P11 cleanup. `VITE_FEATURE_PERSONALIZATION` must not be enabled anywhere a real family can
  reach it until this has merged, or the app tells a child a made-up name was chosen and then shows
  them their own.
- **Erasure response template.** Per 8.5, the guardian-facing erasure response needs an accurate
  sentence about connected families' already-synced copies. Add it to the Phase 3 erasure work in
  `docs/compliance/coppa-gdpr-remediation-plan.md` rather than improvising it under an Article
  12(3) clock.
- **Retention table row.** The same plan's retention table (`:710-719`) needs a row for
  personalization slot values and one for ring-2 consent evidence.
- **Privacy model.** The four entries specified in 5.6.
- **ADR-018 / P7-08.** This feature is a new processing purpose **and** new collection. It adds no
  new provider counterparty, which is the good news, but it changes the privacy notice, the data
  classification, and the App Store nutrition labels.
- **ADR-016 amendment.** One edit, not two. PR #415's B6 wants a sentence recording ring-2
  attribution granularity; this feature wants ring-2 personalization granularity recorded
  alongside it. Whoever writes it writes both. A proposed-addendum block flagging exactly this is
  already parked in ADR-016's ring-2 section.

## 13. Risk register

| ID | Risk | Severity | Mitigation | Phase |
|---|---|---|---|---|
| **R1** | **Sentinel forgery in prose.** The fill LLM emits an extra, mutated, or relocated sentinel; a human approves a blob containing an unreviewed substitution point | High | The P2 exact-multiset, per-node integrity check, fail-closed, run before the approval queue and again after any repair | P2 |
| **R2** | **A guard point is missed on a new surface.** The 29th router serializes a blob title without stripping | High | One shared strip helper at the serialization boundary, not per-call-site strips; a test enumerating title-bearing response models | P3 |
| **R3** | **Offline cache poisoning across siblings.** A future change adds a profile dimension to the story response and the shared `id@version` key starts serving one sibling's copy to another | High | The architecture prevents it, but nothing enforces it. Add a test asserting the story response is byte-identical for two profiles with different toggle states | P6 |
| **R4** | **Slot values are under-validated.** `display_name` is length-bounded free text only (`api/schemas.py:1032-1034`), written straight to the row (`api/profiles.py:102-103`, `:286`), while sibling fields that reach a prompt are far stricter (`PinCode` at `:1038`, banned themes at `:1050-1051`) | High | Apply `structural_value_violations` plus the band-mandatory denylist floor **twice**: at write time and at payload-build time. The second is not redundant: names set before this feature shipped were never checked | P4, P6 |
| **R5** | **Revocation residue.** A device retains a synced values payload after a flag flip or consent revocation | Medium | Purge on flip, revoke, deactivation, sign-out, and policy-version change. Document the offline-device window in code and keep guardian copy prospective | P6 |
| **R6** | **Ring-2 disclosure exceeds what the connection consented to.** A guardian who consented to recommendation attribution finds their child's name throughout another household's story prose | High | A separate consent record per (profile, connection) enumerating covered slot types (5.3), enforced as predicate condition 6 (8.4). Model confirmed 2026-07-25 (ADR-023 OD-1); counsel sign-off still pending | P4, P7, P9 |
| **R7** | **Pronoun outing at ring 2.** A pronoun disclosure reveals something about a child to extended family that the guardian did not intend | High | Pronouns are ring 1 only, enforced by a DB CHECK (5.1) **and** by predicate condition 7 (8.4), not by UI convention. Plus the child-facing off switch | P4, P7, P9 |
| **R17** | **A sibling's name crosses ring 2 against that sibling's own settings.** Sibling B's name rides out inside sibling A's book because only A's consent was checked | High | Predicate condition 8 (8.4): the sibling slot resolves at ring 2 only if the **referenced** profile's own ring-2 enablement and consent cover that connection. Tested in all four A/B combinations (8.6) | P7 |
| **R18** | **The ring-2 slot set grows by drift.** A future slot type is added with `ring2_enabled` allowed because the DB CHECK's set was widened casually | Medium | The ring-2-eligible set is a DB CHECK enumerating slot types (5.1), so widening it is a migration with a reviewer, not a config change. ADR-023's taxonomy section records the reasoning for each current ceiling so a change has something to argue against | P4 |
| **R19** | **An authz-predicate bug leaks a value to an unconnected family.** A wrong join direction, a loosened condition, or a mis-resolved connection returns Alex's details to a household with no edge to the Ruiz family | High | Eight explicit conditions evaluated as Python booleans per row rather than as SQL a refactor can loosen (the house convention at `recommendations.py:214-221`); a dedicated `authorize_via_connection` helper never merged into `authorize_family`; a `ROUTE_TABLE` row in `tests/integration/test_authz_matrix.py`; and the 8.8 test asserting an unconnected family's response is indistinguishable from a non-personalized book. Note this route is the single highest-consequence authz surface the feature adds | P7 |
| **R20** | **Shared-device sibling access to another child's values.** Two sibling payloads live in the same origin's IndexedDB, so a determined reader with devtools, or a sibling who switches profiles, can reach values the application would not render for them | Medium | **Accepted for v1 (owner decision, 2026-07-28)**: a shared family device is a shared trust boundary; the acceptance is recorded in the DPIA/privacy-model entries rather than silently inherited. The store holds compact per-child personal details, a different exposure from the device-wide `storybooks` cache (generic content, identical for everyone) even though both are origin-scoped. Options if a later release must close it: per-profile encryption keyed on the profile PIN, or holding values in memory only and refetching per session. See resolved question 3 | P6 |
| **R8** | **English-only morphology produces bad prose.** "a Maya", possessive edge cases, and verb agreement break substituted sentences | Medium | v1 is English only and scoped to she/her and he/him (agreement-identical pairs). they/them is deferred because singular "they" changes verb conjugation ("she runs" vs "they run"), which a token swap cannot retrofit onto already-conjugated stored prose. Prefer name slots in dialogue and ending titles | P1, P10 |
| **R9** | **Two rendering implementations drift.** The client resolver and the server-side strip helper disagree about what a sentinel is | Medium | One canonical sentinel definition. Carry it in the OpenAPI schema so the generated client picks it up and the CI `contract` job (`ci.yml:432`) fails on drift, rather than letting the frontend re-derive the regex | P1, P3, P5, P6 |
| **R10** | **Consent records leak values into the event log.** A contributor adds the substituted name to a consent event payload for debuggability | Medium | The `_PAYLOAD_ALLOWLIST` mechanism (`events/writer.py:17-19`) already rejects unlisted keys. Write the new entries with keys only, and add a test asserting a value-bearing key is rejected | P3, P4 |
| **R11** | **A real name lands in an antagonist or comic-mishap role.** A sibling name is bound to a `COMPANION`-style slot the skeleton later treats badly | Medium | `role_safety` metadata on the slot spec (2.2), audited per skeleton alongside the pronoun audit | P1, P10 |
| **R12** | **Sentinels reach a rescreen classifier as unfamiliar tokens** and shift scores against the pre-migration baseline | Low | Strip to generic default before classification (3.3), so scores stay comparable | P3 |
| **R13** | **The ADR-016 amendment gets written twice, racing.** This workstream and PR #415's B6 residual both edit the same document | Low | Single owner, single edit covering both asks; the parked addendum in ADR-016 says so | P11 |
| **R14** | **Sentinel survival through the fill LLM is worse than assumed**, making retries a real cost line or the approach unworkable | High | **REALIZED 2026-07-28: measured 3.3% clean on the primary provider (see 3.4). The fallback is now the plan**: deterministic post-fill re-insertion replaces prompt-preserved sentinels as the primary design; Stage B+ re-plans around it | P2 |
| **R15** | **The cross-family endpoint becomes the precedent for loosening `authorize_family`.** A future contributor generalises `authorize_via_connection` into something broader | Medium | Keep it a separate, narrowly-named helper with its own `ROUTE_TABLE` row (8.4); never widen `authorize_family` itself | P7 |
| **R16** | **Ring-2 personalization has no book-delivery path narrower than the catalog.** `Visibility` is `family` or `catalog` only (`publishing/state_machine.py:45-55`) | Medium | Not a blocker: the values gate protects the content regardless of book visibility, so a catalog book renders generic for everyone unconnected. **Accepted for v1 on 2026-07-25 (owner choice, ADR-023 OD-4)**: the catalog surface is the v1 delivery path and connection-scoped visibility is explicitly not a prerequisite | P7 |

## 14. Open questions

### Closed 2026-07-25 by owner decision

Every owner-level question this plan was waiting on has been answered. Recorded here rather than
deleted, so a reader who arrives via an older reference does not think they are still open. Full
records are in ADR-023's "Owner decisions" section.

1. **ADR-023 OD-1 through OD-5: all confirmed as designed (owner choice, 2026-07-25).** Ring-2
   separate disclosure consent (OD-1), pronouns stored not inferred and ring-1 only (OD-2), Route A
   copy drafted by this ADR for #415 to adopt (OD-3), the catalog surface accepted for v1 with
   connection-scoped visibility explicitly not a prerequisite (OD-4), and all three parts of the
   sibling and pet-name raise (OD-5). **Counsel confirmation on OD-1 and OD-5 remains outstanding**
   and is what keeps ADR-023 at Proposed; nothing in this plan is blocked on it, but P7 and P9
   should not ship ahead of it.
2. **Whether the 3-5 band should be offered personalization: confirmed as designed (owner choice,
   2026-07-25).** Offered, guardian-controlled, with no child-facing control rendered at that band.
   No change to section 10.2.
3. **Whether pronouns need a new profile field: answered by OD-2.** They do. The value is an
   explicit guardian-set field, deliberately **stored rather than inferred**, which is the safer of
   the two given this app's standing posture against inferring anything about a child. That makes
   it new child-data collection, so it needs its own privacy-model classification entry alongside
   the others in 5.6, not a footnote on the disclosure question.
4. **Whether narrowing a consent's scope requires re-signing: answered by OD-5(c).** It does not.
   Narrowing updates the signed record in place; only widening triggers re-consent. Section 5.3
   already describes this behaviour and is now confirmed rather than provisional. The honest
   residual, still worth stating in the DPIA, is that after a narrowing the stored artifact is a
   signature over a superset of the current scope.

### Genuinely still open

1. **PR #415 A11 shuffle semantics.** Whether the shuffle changes what is stored or generated, or
   is purely a cosmetic client-side choice among generic names. If it changes the stored bound
   value it touches the same slot the personalization sentinel occupies, and P1 must be sequenced
   against it. That plan lists this as an open user-testing question, not a decision, and OD-3
   deliberately did not resolve it: the copy decision was settled, the shuffle question was not.
2. **The exact sentinel delimiter.** Section 2.3.2 now proposes `{~HERO:Explorer~}` and discharges
   all four constraints against the live code, so this is a recommendation awaiting implementation
   rather than an open design question. Confirm it in code when writing the P2 check.
3. **Shared-device isolation of the values store (risk R20). RESOLVED 2026-07-28 (owner):
   accepted for v1.** A shared family device is a shared trust boundary; no per-profile
   encryption and no in-memory-only mode ship in v1. The acceptance must be recorded in the
   DPIA/privacy-model classification entries when P4's data-classification work lands (see the
   execution plan, Tasks A6 and B7), not silently inherited. The prior framing of the question
   is preserved below for the record: two siblings' values payloads live in one origin's
   IndexedDB with no isolation beyond application logic; the exposure is one sibling learning
   another's pet name, which differs from the `storybooks` cache (generic content identical for
   every reader). Options if a later release must close it: per-profile encryption keyed on the
   profile PIN, or holding values in memory only and refetching per session.

## 15. Related

- [ADR-023](./adr/adr-023-story-personalization-slots.md): the decision record this plan
  implements, including the closed slot taxonomy and the parallel-workstream coordination asks.
- [ADR-016](./adr/adr-016-recommendation-sharing-social-boundary.md): the three rings, the ring-3
  exclusion, and the parked ring-2 granularity addendum.
- [ADR-018](./adr/adr-018-childrens-privacy-compliance.md): the consent-event pattern and P7-08.
- [ADR-019](./adr/adr-019-parameterized-skeletons-theme-contracts.md): the slot machinery P1
  extends.
- [ADR-014](./adr/adr-014-device-authorized-kid-access.md): the device-grant and child-session
  model section 8.4 works within.
- [ADR-012](./adr/adr-012-supabase-cli-migrations.md): migrations are Supabase CLI SQL, not
  Alembic.
- [coppa-gdpr-remediation-plan.md](../compliance/coppa-gdpr-remediation-plan.md): Section 2 bullet
  3 and Section 5 "Self-naming" (Route A), the retention table, and the proposed messaging caveat.
- [privacy-model.md](./privacy-model.md): needs the four classification entries in 5.6.
- [capability-register.md](./capability-register.md): G18 and K20 (minted v1.8); flip both from ❌
  when the work lands and link the covering tests.
