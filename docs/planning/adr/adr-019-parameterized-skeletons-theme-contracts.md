---
title: "ADR-019: Parameterized skeletons and machine-readable theme contracts"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Ratify the WS-2 parameterization scheme before the catalog migration: slotted
  skeletons whose beats guidance, ending titles, and choice-label templates carry
  {SLOT} tokens; a machine-readable per-skeleton theme contract with deterministic
  per-slot constraints validated before any fill; the rule that leaf prose is always
  generated fresh per node and never produced by substitution; the label policy
  (labels are content with a frozen action-semantic); and coexistence of fixed and
  parameterized skeletons during an incremental, non-breaking migration."
tags:
  - planning
  - architecture
  - decisions
  - generation
  - validation
  - diversity
---

# ADR-019: Parameterized skeletons and machine-readable theme contracts

> **Status**: Accepted (2026-07-19; ratified by supervisor sign-off, recorded in
> `docs/planning/ws2-parameterized-catalog-design.md` section 13, before the catalog
> migration begins)
> **Date**: 2026-07-19
> **Relates to**: [ADR-011](./adr-011-story-scale-framework.md) (the constraint grammar
> is the frozen safety object; parameterization varies content strictly inside it),
> [ADR-005](./adr-005-mandatory-human-approval.md) (human approval still gates every
> published story; nothing here adds or removes a human step),
> [ADR-001](./adr-001-story-format-json-storybook.md) (the Storybook schema is
> unchanged; contracts live outside the story document),
> [ADR-010](./adr-010-modal-review-and-gated-generation.md) (the deterministic gate +
> moderation review remain mandatory for every fill). Companion analysis:
> `docs/planning/ws0-label-fingerprint-evaluation.md` (the labels-are-leaves decision
> this ADR's label policy builds on) and `docs/planning/story-flexibility-plan.md`
> section 5 (WS-2) and section 9 (the ADR-019 candidate bullet this ADR resolves).
> Implementation spec: `docs/planning/ws2-parameterized-catalog-design.md`.

## TL;DR

Every skeleton in `skeletons/` will gain a sidecar **theme contract**
(`skeletons/<band>/<slug>.contract.json`, a Pydantic-validated JSON document) that
declares the skeleton's **slots**: the named positions in its beats guidance, ending
titles, and choice-label templates that a theme may re-bind (world, cast, props, tone).
Each slot carries **machine-checkable constraints** (word caps, character-set rules,
band-mandatory term denylists, sibling distinctness, legacy-lexicon leak checks) that a
new **deterministic pre-fill slot validator** enforces, fail closed, before any fill
LLM call is spent. A small **binding step** turns the free-text theme brief (fenced as
untrusted input) into a concrete slot-value map; the validated values are rendered into
a **bound skeleton** (beats guidance, ending titles, label templates only), and the
existing fill pipeline then writes **fresh prose per node** against that bound
skeleton. Slot values are never string-substituted into final reader prose. Safety for
any conforming theme is enforced by the per-slot deterministic constraints, by the
ending kind/valence set baked immutably into the skeleton structure, and by the
existing `validator/` gate plus `moderation/` review on the generated story; no new
human theme-review step is added. Fixed (free-text) and parameterized skeletons
coexist: a skeleton without a contract keeps the current WS-1 fill path byte-for-byte,
so the migration of all 59 catalog files is incremental and non-breaking.

## Context

### Where the pipeline stands

The automated fill already themes stories from the requester's brief: `worker.py`
routes any job whose `authoring_metadata` carries a string `skeleton_slug` into
`_run_skeleton_fill` (`src/cyo_adventure/generation/worker.py:954-965`), which reads
`authoring["theme_brief"]` (`worker.py:275`, written by
`story_requests/authoring_plan.py:510`) and calls
`orchestrator.fill_skeleton` (`worker.py:313-321`). The fill prompt
(`generation/templates/fill.md`, strengthened by WS-1 D2) instructs the model to
re-imagine every passage for the theme and forbids prose that would survive a
find-and-replace of setting nouns (`fill.md:43-57`), with the brief fenced as
`UNTRUSTED_USER_INPUT` (`fill.md:106-113`). The brief's premise is the raw request
text (`story_requests/brief.py:187`).

What is missing is **auditability and per-slot safety**: the reskin is bounded only by
prose instructions and post-hoc review. Nothing machine-checks, before the fill, that
the theme's concrete gate obstacles, prizes, hazards, or deadlines respect the band's
fail-state policy; nothing records which concrete values a theme bound into which
structural positions; and Stage 1 fidelity review must judge a reskin with no
structured statement of what was allowed to change, producing false positives that
burn the shared `max_repairs=3` budget
(`story-flexibility-plan.md:303-319`).

### What the pilot proved

The parameterized-beat pilot (`out/pilot/`) rewrote the 8-11 skeleton
`the-cave-of-echoes` (64 nodes, 16 endings) into a slotted form: 73 slots across
global, route, track, and ending scopes, placed in the `beats='...'` guidance of every
FILL directive and in every ending title (`out/pilot/_neutralize.py:20-335`), with a
prose contract documenting per-slot meaning and constraints
(`out/pilot/cave-of-echoes.theme-contract.md`). Two agent fills for wholly new themes
(space station, dinosaur dig) both passed `check_fill_integrity` and the full gate
(`out/pilot/RESULTS.md:9-25`). The decisive safety observation
(`RESULTS.md:22-25`): the 8-11 no-death guarantee held automatically for both themes,
because the ending `kind`/`valence` set is baked into the fixed structure and no slot
can change it. The gate's PL-15 rule enforces the per-band forbidden ending kinds
deterministically (`validator/policy.py:108-134`;
`validator/band_profile.py:38-92` forbids `death` for 8-11 and `death` + `capture`
for 3-5 and 5-8).

The pilot also exposed three gaps this ADR resolves:

1. **It froze choice labels** (out of scope for a beats-only transform), so labels
   still carried sea-cave nouns that new themes had to bridge awkwardly in prose
   (`RESULTS.md:27-44`). Since then the labels-are-leaves decision shipped (PR #300):
   `diversity/structure.py:83-102` strips `choices[].label` from
   `structure_fingerprint`, `scripts/check_fill_integrity.py:60-82` treats labels as
   leaf content, and the Stage 1 reviewer now checks per-choice label intent
   (`moderation/fidelity_review.py:1-18,35-43`). Labels are content with a **frozen
   action-semantic**, not frozen strings, so label parameterization is unblocked.
2. **Its fills left ending titles as literal slot tokens** (verified:
   `out/pilot/fills/the-cave-of-echoes.space-station.filled.json` still carries
   `"title": "{A1_PRIZE1}"`), because nothing rendered the bindings into the skeleton
   before the fill. The production design must perform that render deterministically.
3. **Its contract was prose**, readable by humans and agents but not machine-checkable,
   so "validation before fill" (`cave-of-echoes.theme-contract.md:171-186`) was a
   convention, not a gate.

### The constraint the design must not violate

`story-flexibility-plan.md:311-315` and safety invariant 3 (`:385-388`): the contract
**bounds and audits** the reskin; leaf prose is still **generated fresh per node**,
never filled by lookup, or the scheme becomes exactly the dog-for-cat template the
WS-0 anti-template guard (now live as an advisory moderation check,
`moderation/leaf_diversity.py`) is built to fail.

## Decision

### 1. Parameterization scheme: slots in guidance, never in prose

A **parameterized skeleton** is a normal, gate-valid skeleton
(`generation/skeleton.py:25-46` loads it through the unchanged blocking gate) whose
theme-specific content positions are replaced by `{SLOT}` tokens
(`{[A-Z][A-Z0-9_]*}`) in exactly three places, and nowhere else:

- the `beats='...'` guidance segment inside `<<FILL role=... words=... beats='...'>>`
  node bodies (`role=` and `words=` are never slotted);
- ending `title` strings;
- choice `label` strings (now legal, per the labels-are-leaves decision).

Node ids, choice ids and targets, conditions, effects, `is_ending`, ending
`id`/`kind`/`valence`, `variables`, `start_node`, and all `metadata` are never
slotted and never touched. A slot changes content, never shape
(`cave-of-echoes.theme-contract.md:3-8`). Structural identity between the original
and parameterized skeleton is asserted with `structure_fingerprint` equality
(`diversity/structure.py:83-102`, which strips exactly the three slotted surfaces).

### 2. The theme contract: a machine-readable sidecar file

Each parameterized skeleton has exactly one contract at
`skeletons/<band>/<slug>.contract.json`, schema-validated by new Pydantic models
(`ThemeContract`, `SlotSpec`, `SlotConstraints`, `SlotScope`) in a new pure module
`src/cyo_adventure/storybook/theme_contract.py`. Per slot: `id`, `scope` (closed enum
`global | route | track | ending`), human `meaning`, advisory `guidance`, and
machine-checkable `constraints`. Per contract: `skeleton_slug`, `age_band`,
`contract_version`, `legacy_lexicon` (the original theme's proper nouns and setting
terms, used as a deterministic leak denylist), and `default_binding` (the original
theme's slot values, the golden fixture and the no-theme fallback).

A sidecar file is chosen over the two alternatives considered:

- **Embedded in the skeleton JSON**: rejected. `Storybook` and `StoryMetadata` are
  `extra="forbid"` (`storybook/models.py:463,212`), so any embedded contract block
  fails the L1-1 schema check that `load_skeleton` runs at load
  (`generation/skeleton.py:38-46`); loosening the reader-facing schema for
  authoring-time data is backwards, and the contract would be copied into every
  persisted `StorybookVersion` blob for no benefit.
- **A database table**: rejected. Skeletons are git-versioned files, discovered by a
  filesystem scan (`generation/skeleton_match.py:42,121-130`) and reviewed by PR; the
  contract must version and review atomically with the skeleton it constrains, and
  the offline tooling (`scripts/run_story_gate.py`, `scripts/check_fill_integrity.py`,
  the cyo-author skill) must work with no database.

The catalog scanner's `band_dir.glob("*.json")` (`skeleton_match.py:127`) is amended
to skip `*.contract.json` so sidecars are never mistaken for skeletons.

### 3. Deterministic contract validation is the safety mechanism (no new human step)

Safety for any conforming theme rests on three deterministic legs, and only these:

1. **Pre-fill slot validation, fail closed.** A new pure checker
   (`validator/slots.py::validate_slot_bindings`) verifies every binding against the
   contract before any fill call: completeness, structural character rules (single
   line, no `{`/`}`, no `<<`/`>>`, no control characters, no U+2014, bounded length),
   word caps, term denylists (with a band-mandatory minimum unioned in for the young
   bands, so a contract-authoring omission can never open a hole), sibling
   distinctness, and legacy-lexicon leak. A violating binding blocks the fill before
   the fill-LLM spend.
2. **The fixed ending kind/valence set.** No slot exists on `ending.kind`,
   `ending.valence`, or any structural field, so no theme can alter the fail-state
   surface PL-15/PL-16/PL-17 verify (`validator/policy.py:98-134`). This is what the
   pilot demonstrated end to end.
3. **The existing post-generation gate and review.** Every fill still runs the full
   `validator/` gate (`validator/gate.py:76-150`) and the `moderation/` pipeline, and
   still requires human approval to publish (ADR-005). Parameterization adds a gate,
   it removes none.

Constraints that are semantic rather than lexical ("retreat is always safe", "wonder
over dread") are carried as advisory `guidance` strings injected into the binding and
fill prompts, and are enforced downstream by legs 2 and 3, not claimed as
deterministic. The contract format records this split honestly per slot.

### 4. Leaves are generated fresh; substitution is prompt-side only

The **only** substitution in the system is the deterministic render of validated slot
values into the skeleton's three guidance surfaces (beats text, ending titles, label
templates), producing a **bound skeleton** that is handed to the existing
`fill_skeleton` pipeline (`generation/orchestrator.py:712-839`). Node prose is written
fresh by the model for every node, under the unchanged WS-1 re-imagine contract
(`fill.md:43-57`); slot values reach prose only as beat guidance inside the prompt,
exactly as the pilot placed them (`cave-of-echoes.theme-contract.md:3-8`). Rendered
ending titles are final and frozen for the fill (they are short names composed from
validated values, not prose). Rendered labels are theme-correct **guidance**: the fill
still writes the final label text, and the Stage 1 label-intent reviewer verifies the
final label preserves the bound label's action-semantic
(`moderation/fidelity_review.py:35-43`). A parameterized fill whose node bodies could
be produced by lookup would fail the anti-template guard, which remains in force
unchanged (`moderation/leaf_diversity.py:119-213`).

### 5. Label policy: content with a frozen action-semantic

Ratified as already decided by the labels-are-leaves evaluation and shipped in PR
#300: a choice's edge, target, condition, and action-semantic are structure; the label
string the child reads is a leaf. Therefore label templates in a parameterized
skeleton carry slots for the theme-supplied object of the action ("Look closely at
{B2_OFFER1}") while the verb frame preserves what choosing does, and the final label
is model-written content checked by Stage 1 label intent. The pilot's label freeze is
formally superseded.

### 6. Binding from a free-text request, fenced as untrusted

The production brief is free text (`brief.py:187`). A new bounded LLM binding step
("bind this brief to these slots, honoring each constraint") emits a slot-value map as
JSON; the deterministic slot validator then accepts or rejects it (with a small
bounded retry carrying the violation list), and only a validated map reaches the
render. The brief is fenced as `UNTRUSTED_USER_INPUT` in the binding prompt exactly as
in `fill.md:106-113`, and the resulting slot values, being derived from untrusted
input (safety invariant 4, `story-flexibility-plan.md:389-392`), are injected into
later prompts only as labeled data, with the structural character rules
deterministically preventing prompt-structure injection (no braces, no directive
markers, single line). Full request interpretation remains WS-7; this step produces
validated bindings and nothing more.

### 7. Coexistence now, full migration as the target

Dispatch is per skeleton, decided by the presence of the contract sidecar: with a
contract, the job binds, validates, renders, and fills the bound skeleton; without
one, the job takes the current WS-1 free-text fill path with byte-identical prompts.
A skeleton containing `{SLOT}` tokens but lacking a contract (a half-migrated state)
fails closed at load. The end-state is a fully parameterized catalog (all 59 files,
56 production plus 3 MVP/test); until then both paths are production paths, and
migration order is free. The migration recipe and acceptance bar are specified in
`docs/planning/ws2-parameterized-catalog-design.md` (Phase C).

## Consequences

### Positive

- **Per-slot, per-band safety becomes deterministic and pre-spend.** A lethal gate or
  prize binding is rejected by code before the fill call, instead of relying on prose
  instructions plus post-hoc review; the young-band denylists are unioned in by the
  validator itself, so no contract author can forget them.
- **The reskin becomes auditable.** The persisted job report records the contract
  version, its hash, and the exact slot bindings, so a reviewer can see precisely
  what the theme changed and Stage 1 has a structured statement of intended variation
  (expected payoff: anti-template distance up, Stage 1 false-positive rate down,
  `story-flexibility-plan.md:316-319`).
- **Labels stop fighting the theme.** The pilot's forced in-prose bridging of
  off-theme label nouns disappears; label guidance is theme-correct by construction
  while action-semantics stay verified.
- **WS-7 and WS-8 get their substrate.** Request interpretation can consume per-slot
  dispositions, and the catalog flywheel can promote new trees through the same
  neutralize-and-contract machinery.

### Negative / accepted costs

- **One extra LLM call per parameterized fill** (the binding step; small, JSON-only,
  bounded retries), plus a new failure mode (binding that cannot satisfy the
  contract) which fails the job closed rather than degrading silently.
- **59 contracts must be authored and maintained.** Contract quality varies with the
  authoring agent; the deterministic acceptance scripts and the band-mandatory
  denylist union bound the blast radius of a weak contract, but meaning/guidance text
  quality still needs per-wave review.
- **Two fill paths exist during migration.** Mitigated by making dispatch a pure
  function of the sidecar's existence and by keeping the legacy path byte-identical.
- **Denylists are lexical.** A determined euphemism can slip a hostile concept past a
  word list; that residual risk is exactly what legs 2 and 3 (fixed ending set, full
  gate + moderation + human approval) exist to catch, and is why the deterministic
  claims are scoped to what word-level checks can actually guarantee.

## Alternatives considered

1. **Free-text theming only (status quo, WS-1 endpoint).** Keeps working, but leaves
   theme safety as prose instruction plus review, is unauditable per slot, and cannot
   feed WS-7 dispositions. Rejected as the end-state; retained as the coexistence
   path.
2. **Slot substitution into final prose (a true template engine).** Cheapest and most
   deterministic, and categorically rejected: it is the dog-for-cat failure the ATG
   exists to fail, and it would collapse leaf diversity, the primary lever of the
   whole plan (`story-flexibility-plan.md:69-73,311-315`).
3. **Slot-value libraries ("packs") as the binding source instead of an LLM binding
   step.** Curated packs (cast packs, tone packs) remain compatible with this design
   as pre-validated bindings, but packs alone cannot serve the actual product input,
   a child's free-text request; the binding step is required regardless. Packs are
   deferred to a later increment on top of this contract format.
4. **A new human theme-review step per theme.** Explicitly ruled out by the owner:
   deterministic contract validation is the chosen safety mechanism, and ADR-005's
   human approval of the finished story already provides the human eyes where they
   matter. The pilot's evidence supports this: safety held structurally, not
   editorially.
5. **Embedding contracts in skeleton JSON or a DB table.** Rejected for the schema,
   provenance, and offline-tooling reasons in Decision 2.
