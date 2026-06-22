---
title: "Phase 2 Implementation Plan (Validation Gate and Authoring Pipeline)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "docs/planning/PROJECT-PLAN.md (Phase 2), roadmap.md, tech-spec.md, validator-rules.md, configuration-cap.md, runtime-semantics.md, drafting-guide.md, stage-prompts/*, adr/003-006"
purpose: "Execution plan for Phase 2: the Layer-2 state-space validator, the combined validation gate, and the staged generation orchestrator (mock-provider, live wiring deferred)."
tags:
  - planning
  - roadmap
  - project
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan work-package by
> work-package. Each work package is executed test-first (TDD): write the failing test, run
> it red, implement minimally, run it green, commit. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the validation gate the arbiter of generated stories: add the Layer-2
state-space validator, a combined gate runner, and a staged generation orchestrator with a
bounded repair loop, all provably correct against a mock provider and a curated corpus, with
no external network egress.

**Architecture:** The Layer-2 validator is a breadth-first closure over `(node, var_state)`
configurations that **reuses the existing pure `StoryEngine`** as its transition function, so
the validator and player can never disagree. The generation orchestrator drives three staged
passes (Structure, Prose, Repair) behind a `GenerationProvider` protocol; Phase 2 ships only a
deterministic `MockProvider`, and an async RQ worker exposes generation through guardian-only
API endpoints. Live provider adapters (Claude/Ollama/OpenRouter) and the 60% live-yield
measurement are deferred (see Scope Boundary).

**Tech Stack:** Python 3.12 (3.10-3.14 in CI), Pydantic v2, networkx, SQLAlchemy 2.x async +
Alembic, FastAPI, RQ + Redis (async worker), textstat (reading level), pytest + testcontainers.

---

## Context

CYO Adventure is a family choose-your-own-adventure reader plus content pipeline. Phase 0
locked the specs and the Storybook schema. Phase 1 (PR #4, branch
`feat/phase-1-schema-reader-v2`, under review at the time of writing) delivered the
deterministic player, the Layer-1 graph validator, the reader API, the PWA reader with offline
sync, and a starter fixture corpus. **This plan begins once PR #4 merges to `main`.**

Phase 2 is the project's honest long pole (roadmap "Critical Path"): generation reliability and
the state-space validator absorb most of the iteration. This plan traces every work package to
a Phase 2 acceptance criterion in [PROJECT-PLAN.md](../../planning/PROJECT-PLAN.md) section 5
and adds no scope beyond the source documents, except the two deliberate deferrals recorded
under Scope Boundary.

### Locked decisions (this session)

1. **Live LLM wiring is deferred.** Build and test the entire pipeline against a deterministic
   `MockProvider`. The real `GenerationProvider` adapters and the 60% live-yield measurement
   ship in a follow-up (`feat/phase-2b-live-provider`). Rationale: keeps Phase 2 fully offline,
   deterministic, and free in CI; isolates the cost/key-dependent and flaky-external concerns
   into one small follow-up; and makes the "no child PII reaches the provider" guarantee
   structural (the PII guard is the only egress, and there is no egress in-phase).
2. **Test stories are subagent-authored, not LLM-generated.** A Sonnet subagent authors the
   Tier-2 state corpus, the known-bad corpus, and additional valid fixtures as a one-time,
   checked-in deliverable (WP5). These also seed the `MockProvider`'s canned outputs (WP6).
   They are fixtures, **not** a substitute for the pipeline-yield metric (see Scope Boundary).
3. **Stacked sub-PRs on one integration branch.** Work lands on `feat/phase-2-generation-gate`
   (the branch named in PROJECT-PLAN section 6) as four reviewable sub-PRs (PR-a..PR-d below),
   each green on its own. The integration branch opens the final phase PR once PR-d merges into
   it, or PR-d itself targets `main` if the sub-PRs were merged progressively. (Owner picks the
   exact merge cadence at PR-a time; the work-package order is unaffected.)
4. **Autonomous execution, minimal check-ins.** Run the work packages end-to-end, surfacing
   only on a blocker or at a sub-PR boundary. Mirrors the Phase 1B execution decision.

### Governing specs (read before each work package)

- [validator-rules.md](../../planning/validator-rules.md): rule ids L2-8..L2-12, RL-13,
  SAFE-14, failure-message templates, rule application order, failure-report format.
- [configuration-cap.md](../../planning/configuration-cap.md): the configuration walk, why
  reachable << theoretical, the 100,000 cap, the variable budget.
- [runtime-semantics.md](../../planning/runtime-semantics.md): transition order, `once: true`,
  bounds clamping, hidden choices. The walk must reproduce this exactly (it reuses `StoryEngine`).
- [tech-spec.md](../../planning/tech-spec.md) sections "Authoring Pipeline (staged generation)",
  "Validation gate", "Data Model" (concept, generation_job), "API Specification".
- [drafting-guide.md](../../planning/drafting-guide.md) and
  [stage-prompts/{structure,prose,repair}.md](../../planning/stage-prompts/): prompt scaffolds
  and the node/depth/variable budgets the generator must respect.
- [privacy-model.md](../../planning/privacy-model.md): the data classification and the PII
  constraint on prompts (WP7).
- [adr-003-frontier-llm-generation.md](../../planning/adr/adr-003-frontier-llm-generation.md):
  the `GenerationProvider` interface decision and its mock-provider testing strategy.

### What Phase 1 already provides (reuse map; do not re-derive)

| Need in Phase 2 | Reuse from Phase 1 | Location |
|---|---|---|
| Transition function for the walk | `StoryEngine.start/visible_choices/choose/is_ending` (pure, no I/O) | `src/cyo_adventure/player/engine.py` |
| Reading-state carrier for the walk | `ReadingState` (current_node, var_state, path, visit_set, version) | `src/cyo_adventure/player/state.py` |
| Condition evaluation | `evaluate(condition, var_state)` (total, never raises) | `src/cyo_adventure/storybook/evaluator.py` |
| Report types | `ValidationReport`, `ValidationFinding`, `Severity` (`to_dict`, `errors`, `ok`, `rule_ids`) | `src/cyo_adventure/validator/report.py` |
| Layer-1 gate (runs first) | `validate_layer1(data) -> ValidationReport` | `src/cyo_adventure/validator/layer1.py` |
| Parsed story model | `Storybook` (+ `Node`, `Choice`, `Effect`, `Variable`) | `src/cyo_adventure/storybook/models.py` |
| Provenance columns (already present) | `storybook_version.model/prompt_version/validation_report/moderation_report` | `src/cyo_adventure/db/models.py` |
| Guardian authz seam | `Principal.is_guardian`, `authorize_family`, `Context`, `CurrentPrincipal` | `src/cyo_adventure/api/deps.py` |
| Router registration | `create_app().include_router(...)` | `src/cyo_adventure/app.py` |
| DB integration harness | testcontainers Postgres + seed in `tests/integration/conftest.py` | `tests/integration/conftest.py` |
| Existing fixtures | 7 valid (4 Tier-2) + invalid graph/schema, incl. `stateful_dead_end.json` | `tests/fixtures/storybook/` |

---

## Scope boundary

### In scope (Phase 2)

- Layer-2 state-space validator (L2-8..L2-12) reusing `StoryEngine`.
- Reading-level advisory check (RL-13, textstat) and a SAFE-14 **stub** that always returns no
  findings but establishes the seam (real moderation is Phase 3).
- A combined gate runner that orders L1 -> L2 (Tier-2 only) -> RL -> SAFE per validator-rules
  section "Rule Application Order".
- `GenerationProvider` protocol and a deterministic `MockProvider`.
- Staged orchestrator (Structure / Prose / Repair) with the 3-attempt cap and no-progress abort.
- Concept brief model + PII guard (the only would-be egress path).
- `concept` and `generation_job` DB tables + Alembic migration.
- RQ worker queue and the guardian-only generation/validation API endpoints.
- Subagent-authored Tier-2 state corpus and known-bad corpus, with rejection tests asserting
  correct rule and node attribution.
- A mock-driven yield harness that demonstrates the measurement methodology end-to-end.

### Explicitly deferred (recorded, not silently dropped)

Per CLAUDE.md scope tracing, these two roadmap Phase 2 acceptance criteria are **not** met by
this plan and move to `feat/phase-2b-live-provider`:

1. **"...passes the full gate with zero structural edits at least 60% of the time over a
   20-story sample."** Requires real generations; deferred with the live provider. WP14 builds
   the harness so the follow-up only swaps `MockProvider` for the real one.
2. **Concrete Claude/Ollama/OpenRouter adapters.** The protocol and config seam ship in Phase 2;
   the HTTP clients ship in 2b.

### Out of scope (later phases, unchanged)

Moderation model + per-age-band policy and the publish state machine + guardian approval UI
(Phase 3); library profile-cap enforcement UI (Phase 4a); node editor, TTS (Phase 4b); MinIO
blob storage, Sentry (Phase 5). Code seams (SAFE-14 stub, `moderation_report` column,
`storybook.status`) are left in place so these plug in without rework.

---

## Sub-PR structure (stacked on `feat/phase-2-generation-gate`)

```text
feat/phase-2-generation-gate            (integration branch off main, post-PR#4)
  PR-a  Validation gate                  WP1  WP2  WP3  WP4  WP5
  PR-b  Generation provider + orchestrator  WP6  WP7  WP8  WP9
  PR-c  Async worker + API               WP10 WP11 WP12 WP13
  PR-d  Yield harness + phase exit       WP14 WP15
```

Each PR is independently green (Ruff, BasedPyright strict, pytest >=80% line / 70% branch, 90%
on Layer-2 + orchestrator, Bandit, pip-audit, pre-commit, signed conventional commits) before
the next begins. PR-a has no new runtime dependencies; PR-b adds `textstat` only if WP3 lands
in PR-a (it does) so PR-b adds none; PR-c adds `rq` + `redis`.

---

## PR-a: Validation gate (WP1-WP5)

### WP1: Configuration-walk core (reuse `StoryEngine`)

**Traces to:** L2-8 (configuration walk), configuration-cap.md.

**Files:**
- Create: `src/cyo_adventure/validator/walk.py`
- Test: `tests/unit/test_config_walk.py`

**What it does.** Enumerate every reachable configuration from `(start_node, initial var_state)`
by driving the existing `StoryEngine`. A configuration is keyed for deduplication by:

```python
# config key = (node_id, frozen var_state, visited-once-effect nodes)
ConfigKey = tuple[str, tuple[tuple[str, VarValue], ...], frozenset[str]]
```

**Design decision (resolve here, note for the validator owner).** validator-rules.md L2-8 names
the configuration `(node_id, var_state)`. That key is **not strictly sound for dedup** when a
story has `once: true` on_enter effects: two readers at the same `(node, var_state)` with
different visit histories can diverge later, because a once-effect on some *other* node fires
for one and is suppressed for the other. The fix keys the visited set on
`visit_set ∩ {nodes that carry a once on_enter effect}`. For the common case (no once-effects)
this collapses to exactly `(node, var_state)`, honoring the spec's intent while staying
provably correct. Tag with `# #CRITICAL: data integrity: ...` and `# #VERIFY:` and reference
this decision. If the owner prefers the literal spec key, that is a one-line change isolated to
this module.

**Interface:**

```python
@dataclass(frozen=True, slots=True)
class WalkResult:
    configs: dict[ConfigKey, ReadingState]      # representative state per config
    edges: dict[ConfigKey, list[ConfigKey]]     # config -> reachable successor configs
    capped: bool                                 # True if the cap aborted the walk

def walk_configurations(story: Storybook, *, cap: int = 100_000) -> WalkResult: ...
```

The walk uses a queue of `ReadingState`; for each, compute `engine.visible_choices(state)`, and
for each visible choice `engine.choose(state, choice.id)` to produce the successor state; dedup
by `ConfigKey`; abort and set `capped=True` the instant `len(configs)` would exceed `cap`.
Ending configurations have no successors (`engine.is_ending` true).

**Test obligations (red-first):**
- Linear 3-node story -> 3 configs, no cap.
- `tests/fixtures/storybook/valid/03_tier2_lantern.json`: walk completes; lantern-gated branch
  appears in exactly the configs where `has_lantern` is true.
- A synthetic story with a tiny cap (`cap=5`) -> `capped is True` and the walk stops promptly.
- A story with a `once: true` on_enter effect: two paths into the same node yield distinct
  configs only when the downstream once-effect would differ (guards the soundness decision).

**Acceptance:** walk reproduces engine semantics exactly (no separate transition logic);
`capped` fires deterministically; 90% line coverage on this module.

### WP2: Layer-2 rules (L2-9..L2-12) over the walk

**Traces to:** L2-9 dead-end, L2-10 escape, L2-11 conditional usefulness, L2-12 cap.

**Files:**
- Create: `src/cyo_adventure/validator/layer2.py`
- Test: `tests/unit/test_layer2_validator.py`

**Interface:** `def validate_layer2(story: Storybook) -> ValidationReport` (mirrors
`validate_layer1`). Internally calls `walk_configurations`. Tier gate: if
`story.metadata.tier == 1`, return an empty report immediately (validator-rules: "Layer 2
applies to Tier-2 stories only ... must not produce false failures").

**Rules:**
- **L2-12 (checked first):** if `WalkResult.capped`, emit one `L2-12` error with the cap
  message and stop (the walk is incomplete, so the other rules cannot run).
- **L2-9 dead-end:** any non-ending config with zero visible choices -> `L2-9` error, message
  template with `node_id` and the offending `var_state`.
- **L2-10 escape:** compute the set of configs from which an ending config is reachable over
  `WalkResult.edges` (reverse reachability from ending configs); any reachable config not in
  that set -> `L2-10` error. This subsumes the trap-cycle case at configuration granularity.
- **L2-11 conditional usefulness:** for every choice carrying a non-`None` `condition`, if it is
  visible in no reachable config -> `L2-11` error attributed to `node_id`/`choice_id`.

Use the exact failure-message templates from validator-rules.md so reports are stable for
repair prompts. `var_state` is rendered as a sorted, JSON-serializable mapping.

**Test obligations:** one targeted test per rule using a minimal synthetic Tier-2 story plus the
corpus from WP5 (cross-referenced once WP5 lands). Assert `report.rule_ids()` and the attributed
`node_id`/`choice_id`, not just `report.ok`.

**Acceptance:** each L2 rule fires on its dedicated case and stays silent on a clean story; 90%
coverage on `layer2.py`.

### WP3: Reading-level advisory (RL-13) + SAFE-14 stub

**Traces to:** RL-13 advisory, SAFE-14 seam.

**Files:**
- Create: `src/cyo_adventure/validator/reading_level.py`, `src/cyo_adventure/validator/safety.py`
- Modify: `pyproject.toml` (add `textstat` to runtime deps)
- Test: `tests/unit/test_reading_level.py`, `tests/unit/test_safety_stub.py`

**RL-13:** `def check_reading_level(story: Storybook) -> ValidationReport`. For each node `body`,
compute Flesch-Kincaid grade via `textstat.text_standard(..., float_output=True)` (or
`flesch_kincaid_grade`); compare to `metadata.reading_level.target ± tolerance`; emit
`Severity.WARNING` findings only (never blocks). Skip ending-only short bodies below a small
word-count floor to reduce noise (document the floor).

**SAFE-14 stub:** `def check_safety(story: Storybook) -> ValidationReport` returns an empty
report in Phase 2 but exists so the gate runner (WP4) and the Phase 3 moderation pass share one
call site. Add a module docstring stating it is a Phase 2 stub and Phase 3 replaces the body.

**Acceptance:** RL-13 produces warnings (not errors) and never sets `report.ok = False`; the
stub is wired and covered.

### WP4: Combined gate runner

**Traces to:** validator-rules "Rule Application Order"; tech-spec "Validation gate".

**Files:**
- Create: `src/cyo_adventure/validator/gate.py`
- Test: `tests/unit/test_gate.py`

**Interface:**

```python
@dataclass(frozen=True, slots=True)
class GateResult:
    report: ValidationReport      # merged findings across all layers
    blocked: bool                 # True if any error-severity finding (L1 or L2)
    safety_flagged: bool          # True if any SAFE-14 finding (Phase 3 will populate)

def run_gate(data: Mapping[str, object]) -> GateResult: ...
```

Order: run `validate_layer1(data)`; **if it has errors, stop** (graph must be sound before a
state walk is meaningful, per validator-rules section "Layer 2"). Else parse to `Storybook`,
run `validate_layer2` (Tier-2 only), then `check_reading_level`, then `check_safety`; merge all
findings into one report. `blocked = not report_excluding_safety.ok`. Keep RL warnings and SAFE
flags out of `blocked` (advisory / human-routed respectively).

**Acceptance:** a clean Tier-2 story -> `blocked is False`; an L1 failure short-circuits before
the walk (assert no L2 finding present); an L2 failure on an L1-clean story -> `blocked is True`.

### WP5: Tier-2 state corpus + known-bad corpus (subagent-authored)

**Traces to:** Phase 2 deliverable "Known-bad corpus and Tier-2 state corpus"; acceptance
"rejects 100% of the known-bad and Tier-2 corpora with correct rule and node attribution".

**Files:**
- Create: `tests/fixtures/storybook/invalid/state/*.json` (one per L2 rule)
- Create/extend: `tests/fixtures/storybook/valid/08_*..N_*.json` (additional valid Tier-2 stories)
- Test: `tests/unit/test_corpus_layer2.py`

**Authoring step (subagent).** Dispatch a Sonnet subagent (`subagent_type: general-purpose`,
`model: sonnet`) with the drafting guide, the schema, and validator-rules as context. Required
deliverables, one fixture each, with a short sibling `.md` note naming the rule it targets:
- `silver_door_dead_end.json` -> L2-9 (extend the existing `invalid/graph/stateful_dead_end.json`
  case to a true stateful dead end).
- `trap_cycle.json` -> L2-10 (state-reachable cycle with no escape toward an ending).
- `unsatisfiable_condition.json` -> L2-11 (a conditional choice no reachable config exposes).
- `bound_overflow.json` -> L1-6 reachable transition pushing an int past `max` (graph-layer,
  but belongs to the curated bad set; assert L1 catches it before L2 runs).
- `config_cap_blowup.json` -> L2-12 (enough booleans/dense effects to exceed a *test-lowered*
  cap; the test passes `cap=...` rather than authoring 100k configs).

**Curation step (executor, not the subagent).** Every fixture is validated by a human-reviewed
test, never trusted blind: each `invalid/state/*.json` must (a) pass Layer 1 where intended and
(b) fail the specific L2 rule with the expected `rule_id` and `node_id`. Treat subagent output
as untrusted draft content; fix any fixture that fails its own assertion.

**Test obligations:** parametrized test iterating `invalid/state/*.json` asserting the expected
rule id fires with correct attribution; a test asserting every `valid/*` Tier-2 fixture passes
`run_gate` with `blocked is False`.

**Acceptance:** 100% of the curated bad corpus rejected with correct rule + node attribution;
100% of valid Tier-2 fixtures pass clean.

---

## PR-b: Generation provider + orchestrator (WP6-WP9)

### WP6: `GenerationProvider` protocol + `MockProvider`

**Traces to:** Phase 2 deliverable "Provider interface (Claude primary; ...fallback)"; ADR-003.

**Files:**
- Create: `src/cyo_adventure/generation/__init__.py`, `src/cyo_adventure/generation/provider.py`
- Test: `tests/unit/test_mock_provider.py`

**Interface (structural typing; no provider SDK imported in-phase):**

```python
class GenerationProvider(Protocol):
    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str: ...

@dataclass
class MockProvider:
    """Deterministic provider for tests. Returns queued responses in order;
    a callable response may inspect the prompt to return stage-appropriate JSON."""
    responses: list[str | Callable[[str], str]]
    calls: list[str] = field(default_factory=list)   # captured prompts, for assertions
    async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str: ...
```

`MockProvider` records every prompt in `calls` (so WP7 can assert no PII leaked) and pops
responses in order. Seed canned responses from the WP5 subagent-authored stories (a valid
skeleton JSON for Stage A, a full Storybook JSON for Stage B) plus deliberately malformed
strings (truncated JSON, wrong-shaped skeleton) to drive the repair path in WP8.

**Acceptance:** mock returns queued responses deterministically; `calls` captures prompts; 90%
coverage.

### WP7: Concept brief model + PII guard

**Traces to:** Phase 2 deliverable "Concept intake (no real child PII)"; acceptance "No prompt
sent to the provider contains a real child name, birthdate, or sensitive trait";
privacy-model.md.

**Files:**
- Create: `src/cyo_adventure/generation/concept.py`, `src/cyo_adventure/generation/pii.py`
- Test: `tests/unit/test_concept.py`, `tests/unit/test_pii_guard.py`

**Concept brief (Pydantic v2, `extra="forbid"`):** the intake fields from tech-spec
"Concept brief": `title?`, `premise`, `protagonist` (name/age/role), `point_of_view` (default
2nd person), `age_band` (`AgeBand`), `reading_level_target`, `tier` (1|2), `tone`,
`themes_allowed[]`, `content_nogo[]`, `target_node_count`, `ending_count`, `structure_pattern`
(enum: time_cave | gauntlet | branch_and_bottleneck | quest | loop_and_grow),
`desired_variables[]?`, `special_constraints[]?`.

**PII guard:** `def assert_prompt_pii_safe(prompt: str, *, forbidden: PiiContext) -> None` where
`PiiContext` carries the family's real child names / birthdates pulled from the request context
(never from the brief). Raises `ValidationError` (core hierarchy) if any forbidden token appears.
The orchestrator (WP8) calls this on **every** assembled prompt before handing it to the
provider. This is the only egress chokepoint; tag `# #CRITICAL: security: ...` /
`# #VERIFY: assert_prompt_pii_safe runs on every prompt; test proves it raises`.

`protagonist.name` in the brief is the *story* protagonist, not a real child; document that the
guard checks against the family's real-child names (the leak risk), not the brief's chosen
character name.

**Acceptance:** a prompt containing a seeded real child name raises; a clean prompt passes;
brief rejects unknown fields and out-of-range tiers.

### WP8: Orchestrator (Stage A/B/C) + repair loop

**Traces to:** Phase 2 deliverable "Generation orchestrator with staged passes"; quality gate
"pipeline with mocked provider returning canned and malformed outputs, proving repair loop and
no-progress abort"; 90% coverage on the orchestrator.

**Files:**
- Create: `src/cyo_adventure/generation/orchestrator.py`
- Test: `tests/unit/test_orchestrator.py`

**Interface:**

```python
@dataclass(frozen=True, slots=True)
class GenerationOutcome:
    status: Literal["passed", "needs_review", "failed"]
    storybook: dict[str, object] | None     # decoded final Storybook JSON, if any
    report: dict[str, object]               # final GateResult.report.to_dict()
    attempts: int
    stage_log: list[str]                    # human-readable trail for the job record

async def generate_story(
    brief: ConceptBrief, provider: GenerationProvider, pii: PiiContext,
    *, max_repairs: int = 3,
) -> GenerationOutcome: ...
```

**Flow (validator runs deterministically between every stage; tech-spec "Authoring Pipeline"):**
1. **Stage A (Structure):** assemble the structure prompt (WP9), PII-guard it, call provider,
   parse the skeleton JSON, expand to a minimal Storybook-shaped doc, run `run_gate`. If the
   graph is unsound, go straight to repair (do not spend Stage B tokens).
2. **Stage B (Prose):** assemble the prose prompt from the approved skeleton, PII-guard, call,
   parse full Storybook JSON, run `run_gate`.
3. **Stage C (Repair), bounded:** while `blocked` and `attempts < max_repairs`: assemble the
   repair prompt naming **only** the failing `node_id`s and `rule_id`s from the report (the
   report's `to_dict()` is already this shape), PII-guard, call, re-parse, re-gate. **No-progress
   abort:** if the new report's findings or the output hash equals the previous attempt's, stop
   immediately (an extra attempt cannot help). On exhaustion or no-progress, return
   `status="needs_review"` (never auto-publish, per ADR-005 and the deliverable note).
4. Map outcome: gate clean -> `passed`; safety-flagged-but-otherwise-clean -> `needs_review`
   (Phase 3 owns moderation, but the seam returns the right status now); still blocked ->
   `needs_review` or `failed` per whether any structural output was produced.

No-progress detector: compare `(sorted_finding_tuples, sha256(canonical_json(output)))` between
consecutive attempts.

**Test obligations (all against `MockProvider`, offline):**
- Happy path: Stage A valid skeleton, Stage B valid Storybook -> `passed`, `attempts == 0`
  repairs, `run_gate` clean.
- Repair success: Stage B returns a story with one L2-9 dead end; repair response fixes it ->
  `passed` after 1 repair; assert the repair prompt contained the failing node id.
- Repair exhaustion: provider keeps returning the same broken story -> `needs_review`,
  `attempts == 3`.
- No-progress abort: provider returns an identical broken story twice -> stops at attempt 2,
  not 3 (assert `attempts < max_repairs`).
- Malformed output: Stage B returns truncated JSON -> handled as a gate failure routed to
  repair, never an unhandled exception.
- PII: a brief whose assembled prompt would contain a seeded real child name -> raises before
  any provider call (assert `provider.calls == []`).

**Acceptance:** all six behaviors proven against the mock; 90% coverage on `orchestrator.py`.

### WP9: Stage prompt assembly

**Traces to:** stage-prompts/{structure,prose,repair}.md; drafting-guide.md as `{drafting_guide}`.

**Files:**
- Create: `src/cyo_adventure/generation/prompts.py`
- Test: `tests/unit/test_prompts.py`

Load the three stage-prompt templates (checked-in markdown) and fill their placeholders
(`{drafting_guide}`, concept fields, `{skeleton}`, `{validation_report}`, the failing-node list)
deterministically. Pure string assembly; no I/O beyond reading the bundled template files
(package them under `src/cyo_adventure/generation/templates/` copied from
`docs/planning/stage-prompts/` so runtime does not depend on `docs/`). Assert each placeholder is
filled and the repair prompt enumerates exactly the failing node ids and rule ids.

**Acceptance:** every placeholder substituted; repair prompt names only flagged nodes; no
`docs/` path read at runtime.

---

## PR-c: Async worker + API (WP10-WP13)

### WP10: `concept` + `generation_job` tables + Alembic migration

**Traces to:** tech-spec "Data Model -> Operational entities (Postgres)".

**Files:**
- Modify: `src/cyo_adventure/db/models.py` (add `Concept`, `GenerationJob`)
- Create: `alembic/versions/<rev>_add_concept_and_generation_job.py`
- Test: `tests/integration/test_generation_models.py`

`Concept`: `id (uuid pk)`, `family_id (fk family)`, `brief (JSONB)`, `created_by (fk user)`,
`created_at`. `GenerationJob`: `id (uuid pk)`, `concept_id (fk concept)`, `model (str|None)`,
`provider (str|None)`, `prompt_version (str|None)`, `status (str, default "queued")`,
`report (JSONB|None)`, `storybook_id (str|None)`, `version (int|None)`, `error (str|None)`,
`created_at`, `updated_at`. Follow the existing string-enum-as-validated-string convention (no
native PG enums) and the `_TS` timestamp pattern already in the module.

Generate the migration with `alembic revision --autogenerate` against the testcontainers schema
and hand-verify it (autogenerate is a starting point, not trusted output); record the
down-revision per the TECHNICAL_BASELINE convention. Add a CI migration check only if one does
not already exist (do not duplicate).

**Test obligations (integration, testcontainers Postgres):** insert a concept + job, read back,
assert FK integrity; assert `alembic upgrade head` then `downgrade -1` round-trips on an empty DB.

**Acceptance:** tables created via migration (not just `Base.metadata.create_all`); round-trip
green.

### WP11: RQ queue + worker

**Traces to:** Phase 2 deliverable "RQ worker queue for async generation".

**Files:**
- Create: `src/cyo_adventure/generation/queue.py`, `src/cyo_adventure/generation/worker.py`
- Modify: `pyproject.toml` (add `rq`, `redis`), `src/cyo_adventure/core/config.py` (add
  `redis_url`, `generation_provider: Literal["mock","claude","ollama","openrouter"] = "mock"`)
- Test: `tests/unit/test_worker.py`, `tests/integration/test_generation_queue.py`

`queue.py` exposes `enqueue_generation(job_id) -> str` behind a thin interface so the worker
body is testable synchronously. `worker.py`'s `run_generation_job(job_id)` loads the concept,
builds the configured provider (in-phase: always `MockProvider`; the factory raises a clear
`ConfigurationError` for `claude/ollama/openrouter` with "deferred to Phase 2b"), runs
`generate_story`, and writes the `GenerationOutcome` to the `generation_job` row (status,
report) and, on `passed`, creates a `storybook` + `storybook_version` row with provenance
columns populated (`model`, `prompt_version`, `validation_report`).

Worker DB access uses its own session (not the request unit-of-work); set a correlation id at
job start (`set_correlation_id(generate_correlation_id())`, per the project background-job
pattern). Tag async/external/concurrency RAD markers per `src/cyo_adventure/CLAUDE.md`.

**Test obligations:** unit test runs `run_generation_job` against a fake/in-process queue + mock
provider, asserting the job row transitions `queued -> running -> passed|needs_review` and a
`storybook_version` is written on success; an integration test exercises the real enqueue path
(Redis via testcontainers, marked `integration`, skipped if Docker is unavailable, mirroring the
Postgres harness).

**Acceptance:** worker produces a persisted, provenance-stamped version on success; provider
factory cleanly refuses deferred providers.

### WP12: Generation/validation API endpoints + authz

**Traces to:** tech-spec "API Specification" rows for concepts, generate, generation-jobs,
validate; authorization-matrix.md (guardian-only; IDOR negatives).

**Files:**
- Create: `src/cyo_adventure/api/generation.py`
- Modify: `src/cyo_adventure/app.py` (`include_router(generation.router)`),
  `src/cyo_adventure/api/schemas.py` (request/response models)
- Test: `tests/integration/test_generation_api.py`

Endpoints (all guardian-only; reuse `Context`/`CurrentPrincipal` and `authorize_family`):
- `POST /api/v1/concepts` -> create a concept brief (validate `ConceptBrief`; PII guard the brief
  text against the family's real-child names).
- `POST /api/v1/concepts/{id}/generate` -> enqueue a `GenerationJob`; 202 with job id.
- `GET /api/v1/generation-jobs/{id}` -> status + report (family-scoped).
- `POST /api/v1/storybooks/{id}/versions/{v}/validate` -> re-run `run_gate` on a stored version,
  returning `GateResult.report.to_dict()`.

Child tokens must be rejected (403) on all four. IDOR: a guardian from family B cannot read
family A's concept, job, or storybook (404/403 per the matrix).

**Test obligations (integration):** guardian happy path for each endpoint; child token -> 403 on
each; cross-family guardian -> not-found/forbidden; a generate call enqueues and the job row
appears. Extend the existing seed in `tests/integration/conftest.py` rather than duplicating it.

**Acceptance:** all four endpoints function and enforce family scope + role; IDOR negatives green.

### WP13: Regenerate the frontend API client

**Traces to:** CLAUDE.md Architecture rule "OpenAPI schema is the source of truth for the
frontend".

**Files:** Modify: `frontend/src/client/**` (generated output, do not hand-edit)

After the new routes exist, regenerate: start the backend, then
`cd frontend && npm run generate-client`. Commit the regenerated client as build output. Run
`npm run lint && npm run typecheck` to confirm the client compiles. No hand-written types.

**Acceptance:** generated client includes the generation endpoints; frontend type-check passes.

---

## PR-d: Yield harness + phase exit (WP14-WP15)

### WP14: Mock-driven yield harness (methodology, live deferred)

**Traces to:** acceptance "60% over a 20-story sample" (built now, measured in Phase 2b).

**Files:**
- Create: `scripts/yield_harness.py`
- Test: `tests/unit/test_yield_harness.py`

A runnable harness that takes N concept briefs, runs `generate_story` against a provider, and
reports the pass rate (`passed / N`) with per-story rule-failure breakdown. In Phase 2 it runs
against `MockProvider` seeded from WP5 stories, so it demonstrates the measurement end-to-end and
is unit-tested deterministically (e.g. 8 passing + 2 needs_review canned -> reported 80%). The
follow-up (`feat/phase-2b-live-provider`) swaps the provider and runs the real 20-story sample;
the harness code does not change. Document the run command:
`PYTHONPATH=. uv run python scripts/yield_harness.py --briefs <dir> --provider mock`.

**Acceptance:** harness computes and prints a correct pass rate on canned input; documented run
command works as written (PYTHONPATH explicit).

### WP15: Phase 2 exit documentation

**Files:**
- Modify: `docs/planning/PROJECT-PLAN.md` and `docs/planning/roadmap.md` (mark Phase 2 status,
  note the two deferred criteria and the `feat/phase-2b-live-provider` follow-up)
- Create: `docs/planning/phase-2b-live-provider.md` (a short follow-up spec: implement
  Claude/Ollama/OpenRouter `complete()`, wire `generation_provider` config, run the 20-story
  yield, gate on >=60%)
- Modify: `CHANGELOG.md` (OpenSSF: features documented)
- Template feedback: if any template gap surfaced, append to `docs/template_feedback.md`.

**Acceptance:** roadmap/plan reflect reality (no silently-dropped criteria); follow-up spec
exists so Phase 2b is a small, well-scoped task.

---

## Cross-cutting notes

**Dependencies to add** (one per the PR that first needs it, keep `uv.lock` updated):
`textstat` (WP3), `rq` + `redis` (WP11). No provider SDK (`anthropic`, etc.) in Phase 2.

**Config additions** (`core/config.py`): `redis_url` (dev default localhost, same fail-fast
posture as `database_url` for non-local), `generation_provider` (default `"mock"`).

**RAD markers (mandatory in this package, per `src/cyo_adventure/CLAUDE.md`):** the PII guard
(security), the worker DB session + correlation (concurrency/timing), the provider factory
(external resources), and the walk soundness decision (data integrity) each need a
`#CRITICAL`/`#ASSUME` + `#VERIFY` pair.

**Definition of Done per WP (roadmap):** code reviewed; tests pass (>=80% line, 70% branch; 90%
on Layer-2 + orchestrator); docs updated; Ruff + BasedPyright strict clean; Bandit + pip-audit
no high/critical; signed conventional commits.

---

## Self-review

- **Spec coverage:** every Phase 2 PROJECT-PLAN deliverable maps to a WP: Layer-2 validator
  (WP1-WP2), config cap (WP1-WP2), staged orchestrator + repair (WP8-WP9), provider interface
  (WP6), concept intake + PII (WP7), RQ worker (WP11), known-bad + Tier-2 corpora (WP5),
  validate endpoint (WP12). The two unmet acceptance criteria (60% yield, real adapters) are
  explicitly deferred under Scope Boundary, not dropped.
- **Type consistency:** `run_gate -> GateResult`, `GenerationProvider.complete`,
  `generate_story -> GenerationOutcome`, `walk_configurations -> WalkResult` are referenced
  consistently across WPs. `ValidationReport`/`Severity`/`Storybook`/`ReadingState` reuse the
  exact Phase-1 signatures read from source.
- **Shell commands:** the only documented CLI (WP14) includes `PYTHONPATH=.`; pytest sets
  `pythonpath` itself via `pyproject` so test commands need no prefix; `npm run generate-client`
  runs from `frontend/`.
- **No live-API capability probe needed in-phase:** there is no managed-cloud bulk operation in
  Phase 2 (live wiring deferred); the equivalent probe belongs in Phase 2b before the 20-story run.

---

## Execution handoff

Per the locked decision (autonomous, minimal check-ins): once PR #4 merges, create
`feat/phase-2-generation-gate` off `main`, then execute WP1->WP15 in order via
**superpowers:subagent-driven-development** (a fresh subagent per work package, TDD within each,
two-stage review between WPs). Surface to the owner only at sub-PR boundaries (after WP5, WP9,
WP13, WP15) or on a blocker. The corpus-authoring step in WP5 dispatches a Sonnet subagent as a
fixture factory; its output is curated by a reviewing test before it is trusted.
