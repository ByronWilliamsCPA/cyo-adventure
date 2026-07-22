---
schema_type: planning
title: "WS-8 Design: The Catalog Flywheel (grow the tree catalog with usage)"
description: "Phase A design for WS-8: close the loop from WS-4's cell-saturation
  demand signal to a merged skeletons/ promotion PR, using the delivered WS-5
  mutation engine (bounded composed chains, the unchanged acceptance harness,
  the promotion bundle) as the candidate generator and the ADR-020 decision set
  as fixed law. Automation triggers, generates, accepts, drafts re-guidance,
  assembles bundles, and prepares promotion PRs; a human always performs
  structure approval by reviewing and merging the PR, with no auto-merge ever.
  Feed-agnostic by contract so WS-6 fresh-generated trees plug into the same
  promotion path later; WS-5-mutant-only first value is recommended."
tags:
  - planning
  - generation
  - validation
  - diversity
status: delivered
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give the reviewer and the follow-up implementer an exact, file-by-file
  design for WS-8: the end-to-end flywheel loop with a per-stage interface table
  and an explicit automation boundary, the trigger's persistence as an enum-only
  pipeline event (the current saturation log lacks the full cell coordinate),
  the candidate strategy per saturated cell (parents, chain templates, seed
  budgets, discard-ledger memory, distance-ranked selection), the re-guidance-at-
  scale decision (hybrid agent-draft/human-approve, with a deterministic reguide
  floor and LLM01 fencing), the feed-agnostic promotion-bundle contract (Lineage
  v2 with an origin discriminator for WS-6), the parameterize-at-promotion path
  for contract-less trees, bounded scheduling/cadence, the WS-0-instrumented
  metrics, and a D1-D8 plan ordered cheapest-and-safest first."
component: Strategy
source: "docs/planning/story-flexibility-plan.md section 5 (WS-8, lines 355-361;
  WS-6, lines 349-353; WS-4 status note, lines 250-273), section 6 (sequencing,
  lines 381-399), section 7 (safety invariants, lines 401-419);
  docs/planning/adr/adr-020-mutation-derived-skeletons-and-catalog-growth.md
  (ACCEPTED 2026-07-20: the six binding decisions and the composed-chain
  evidence exhibit); docs/planning/ws5-structure-state-variation-design.md
  (sections 6, 9, 12); docs/planning/capability-register.md (K3 line 112);
  code read 2026-07-20: mutation/{ops,operators,state_ops,acceptance,floors,
  bundle,reguide,compose,contract_gate,sample_fill}.py,
  scripts/{mutate_skeleton,parameterize_skeleton,calibrate_mutation_floors,
  render_skeleton_diagrams,run_diversity_eval}.py,
  docs/planning/ws5_floor_baseline.json (TAU_STRUCT 0.332507, TAU_CELL 0.01
  clamped, TAU_STATE 0.5), generation/{skeleton,skeleton_match,
  skeleton_catalog,diagram}.py, story_requests/authoring_plan.py (the
  selection.cell_theme_saturated emission, lines 423-432),
  diversity/{query,structure,aggregate}.py, events/{writer,models}.py,
  out/pilot/_neutralize.py; skeletons/** (six band dirs, contract sidecars,
  zero lineage sidecars on disk today)."
---

# WS-8 Design: The Catalog Flywheel

> **As-built note (2026-07-21).** This began as the Phase A design below and has
> since been DELIVERED as D1-D8 (see the CHANGELOG `[Unreleased]` entries). The
> body is preserved as the design-time record; where the delivered code deviates
> from it, the delivered code governs. The one substantive deviation: the
> anti-clone floor was recalibrated for mutation-derived candidates. The
> `TAU_CELL = 0.01` clamp and the `TAU_STRUCT` parent-distance gate that several
> sections below describe were superseded by ADR-020 Amendment 1, which retires
> the parent-distance gate and sets `TAU_CELL = 0.05` against the parent and
> in-cell siblings (see `docs/planning/ws8-floor-recalibration-proposal.md` and
> `mutation/floors.py`). Read "proposed" / "nothing here is implemented" / the
> `TAU_CELL = 0.01` references below as historical.

> **Original status: proposed (Phase A).** This document was the input to a
> supervisor sign-off review, mirroring the WS-1, WS-2, WS-5, and WS-7 Phase A
> process. Section 15 listed the decisions the reviewer ratified before the
> implementation pass.
>
> **The paragraph that governs everything else:** WS-8 is a *wiring*
> workstream, not an engine workstream. Every safety-bearing mechanism it uses
> already exists and is consumed unchanged: the WS-5 operators and bounded
> chains generate candidates, the byte-identical acceptance harness (gate,
> cell assertion, Tier-2 walk checks, anti-clone floors, contract acceptance)
> proves them, the promotion bundle packages them, and ADR-020 (accepted
> 2026-07-20, binding) fixes the promotion model: mutants are first-class
> citizens with no inherited trust, lineage is a sidecar, the gate is
> byte-identical plus reject-only floors, **human structure approval is the
> skeletons/ PR review with no auto-merge**, cells are inherited, contracts
> keep parity. WS-8 adds the loop around that engine: a demand trigger read
> from WS-4's saturation signal (consumed as an enum cell coordinate, never as
> theme text, OWASP LLM01), a bounded candidate strategy per saturated cell, a
> resolution path for re-guidance at scale, promotion-PR preparation, and
> WS-0-instrumented metrics that close the loop. The automation boundary is
> absolute: automation prepares PRs, humans merge them (WS-5 CR-1, ADR-020
> decision 4). Nothing WS-8 builds can write under `skeletons/`, weaken a
> floor, or touch the fill -> gate -> moderation -> ADR-005 chain a promoted
> tree's stories still run in full.

---

## 1. Objective and scope

WS-8 per the master plan (`story-flexibility-plan.md` section 5, "WS-8:
Catalog flywheel (highest ceiling)", lines 355-361): **grow the tree catalog
with usage, not authoring budget.** Promote any gate-passed, human-approved
fresh (WS-6) or composed/mutated (WS-5) tree into the parameterized catalog via
the neutralize transform, behind a human structure-approval step. Sequencing
(section 6, line 391): WS-5 feeds WS-8, WS-6 also feeds WS-8; WS-8 consumes
WS-4's saturation signal and WS-0's metrics. Of those four inputs, three are
delivered (WS-0 Phases 1-2, WS-4 request-time consumption, WS-5 D1-D8 plus
ADR-020) and one is not started (WS-6). Section 15 OQ-3 recommends delivering
WS-8's first value on WS-5 mutants alone.

**Capability served** (register IDs, `capability-register.md`):

- **K3 (primary):** "Choices are consequential: paths genuinely differ,
  endings vary, the story remembers state" (line 112). WS-5 built the
  mechanism that grows structural and state variation; WS-8 is the demand loop
  that makes the mechanism run when and where readers actually need it, so K3
  holds up for heavy readers in saturated cells without a standing authoring
  budget.
- **K13 (gate, not served):** the age-band content guarantee bounds every
  promoted tree exactly as it bounds a hand-authored one (section 10).

**Metric (from the plan, line 361):** net new trees per month. Operationalized
with existing instruments only (section 9): merged skeleton-promotion PRs
counted from `*.lineage.json` sidecar additions in git history, the WS-0
distinct-trees-per-cell trend weighted by
`diversity.structure.structural_distance`, and `effective_catalog_size`. WS-8
adds no new metric machinery, only a report that reads what WS-0 computes.

**Explicitly in scope:**

- The end-to-end flywheel loop specification: trigger, candidate strategy,
  acceptance, re-guidance resolution, bundle assembly, promotion-PR
  preparation, merge, measurement (section 4), with a hard automation boundary
  (section 4.3).
- Making the WS-4 trigger consumable: today `selection.cell_theme_saturated`
  logs only `band` and `level` (`authoring_plan.py:428-432`); WS-8 persists a
  full, enum-only cell coordinate (section 4.1, D1).
- The candidate strategy: parent and chain-template selection per saturated
  cell, attempt budgets, discard-ledger memory, distance-ranked candidate
  selection (section 6).
- Re-guidance at scale: the hybrid agent-draft / human-approve model with a
  deterministic reguide floor and LLM01 containment (section 5, OQ-1).
- The feed-agnostic promotion contract: Lineage v2 with an origin
  discriminator so WS-6 fresh trees ship the same bundle (section 7), and the
  parameterize-at-promotion path for contract-less trees via the WS-2 recipe.
- Bounded scheduling: per-cell and global caps, cool-downs, manual-first
  cadence (section 8).
- Metrics and the flywheel report (section 9); the D1-D8 plan (section 12).

**Explicitly out of scope:**

- **Any change to the WS-5 engine.** Operators, `acceptance.py`'s stage
  ladder, `floors.py` thresholds, `compose.py`'s `MAX_CHAIN_LENGTH = 3`,
  `bundle.py`'s writer/verifier, and `scripts/mutate_skeleton.py` are consumed
  as-is. Where WS-8 needs an extension (Lineage v2, a reguide floor) it is
  additive and lands behind its own deliverable.
- **WS-6 itself.** WS-8 defines the feed contract WS-6 must satisfy
  (section 7.2) but builds no fresh-generation pipeline.
- **The grammar-based composer.** Still deferred per WS-5 section 7; a
  composed tree, when it exists, enters through the same feed contract.
- **Auto-merge, an in-app promotion surface, or any promotion path that is
  not a reviewed git PR.** ADR-020 decision 4 is binding; an in-app surface
  was explicitly deferred by that ADR's alternatives section until promotion
  volume warrants it, and this design does not reach that volume (section 8's
  caps guarantee it).
- **Selection changes.** `skeleton_match.py` weights, the WS-4 similarity
  blend, and the `_weight`/`_blended_weight` novelty floor are untouched; a
  promoted tree enters selection as an unused candidate at weight 1.0, which
  is already the mechanism that carries new trees to readers.
- **Catalog deletion or de-duplication of existing trees.** The hygiene
  signal WS-5 surfaced (section 6.5) is reported to the owner, never acted on
  by automation.

**Deliverables:** D1-D8, section 12.

## 2. Current state (the exact seams)

### 2.1 The demand signal exists but is not yet consumable as a cell

`story_requests/authoring_plan.py::_resolve_skeleton_fill` (lines 423-432)
emits, whenever a family's similarity context escalates past tree-level
differentiation, the info log `selection.cell_theme_saturated` with fields
`band` and `level` (`DifferentiationLevel.LEAF` or `.CATALOG`), annotated in
the source as "a signal for the WS-8 catalog flywheel". The escalation ladder
(`diversity/query.py::score_history`, lines 149-159) is deterministic:
`CATALOG` means every candidate slug in the cell has been used for a
similar-theme story for this family AND at least one slug has been used twice.
Two gaps for WS-8:

1. **The log line carries `band` but not `length` or `style`**, so the full
   `(band, length, style)` cell coordinate the flywheel must target is not
   recoverable from the event. Both values are in scope at the emission site
   (`_resolve_skeleton_fill` computed the cell to build `skeleton_alternatives`);
   adding them is a two-field change (D1).
2. **A log line is not a queryable counter.** The flywheel needs "how many
   CATALOG escalations has cell X seen in the last 30 days, from how many
   distinct requests", which means a persisted, append-only record. The
   `events/` package is the established pattern: `events/writer.py` enforces a
   per-event-type payload key allowlist whose contract is "ids, enum values,
   scores, counts, controlled-vocab reasons only; never free text", which is
   exactly the LLM01 posture the trigger needs (section 4.1).

### 2.2 The engine is delivered and its hand-off shape is fixed

WS-5 D1-D8 are merged. The exact seams WS-8 drives:

- **Candidate generation:** `mutation/compose.py::apply_chain` applies a
  bounded chain (1..`MAX_CHAIN_LENGTH = 3` steps of `(op_id, params, seed)`),
  atomic (any step's precondition failure aborts the chain), deterministic
  (byte-identical replay from the recorded chain). `mutation/operators.py`
  registers M1-M4, `mutation/state_ops.py` M5. ADR-020's evidence exhibit and
  the D7 calibration record the load-bearing fact for strategy design:
  **a single structural op usually falls below `TAU_STRUCT` (0.332507), so
  composed chains pairing a structural op with an M2 outcome re-map are the
  value path.**
- **Acceptance:** `mutation/acceptance.py::run_acceptance` (via
  `compose.run_chain_acceptance` for chains) runs the fixed stage ladder:
  stage 0 preconditions, stage 1 the byte-identical `run_gate`, stage 2 cell
  assertion, stage 3 Tier-2 single-walk checks (ending coverage, clock
  re-proof, state-signature floor for shape-unchanged mutants), the
  structural anti-clone floor for shape-changed would-be-promotable
  candidates, stage 4 contract acceptance. Every failure is a structured
  `mutation.discarded` log carrying parent slug and sha256, op chain, params,
  seed, failing stage, and rule ids. A candidate with unresolved re-guidance
  is *held*: it exists but `promotable` is false.
- **Floors:** `mutation/floors.py` loads `TAU_STRUCT = 0.332507`,
  `TAU_CELL = 0.01`, `TAU_STATE = 0.5` from the committed
  `docs/planning/ws5_floor_baseline.json`; reject-only by construction. The
  baseline's `clamps` note records the catalog-hygiene finding WS-8 must
  respect: two existing in-cell siblings sit at structural distance 0.000947,
  and the calibrator clamped `TAU_CELL` up to 0.01 so that pair could never
  justify admitting a clone (section 6.5).
- **Re-guidance:** `mutation/reguide.py` models author resolutions
  (`ResolvedReguide` with a mandatory `author` field), reconciles them against
  emitted items by `target_id`, and its module docstring pins the current
  posture: "The resolution content is ALWAYS author-supplied (design
  principle 6, OWASP LLM01 ...); it never generates guidance text." WS-8's
  section 5 is the deliberate, fenced amendment of exactly that posture, and
  it is the workstream's pivotal open question (OQ-1).
- **The bundle:** `mutation/bundle.py` writes
  `out/mutations/<slug>/` containing the gate-passing shell, the mutated
  contract (parameterized parents), the `*.lineage.json` sidecar
  (`Lineage`: `parent_slug`, `parent_sha256`, `donor_slugs`, `op_chain`,
  `created_at`, `tool_version`, `acceptance_digest`; `LINEAGE_VERSION = 1`),
  `acceptance.json`, `reguide.json` (before/after per item, `fully_resolved`),
  `sample-fill/`, and the diagram. `verify_bundle` recomputes the live
  parent's hash and **hard-fails a bundle whose parent changed since
  derivation**; this is the staleness gate every promotion must re-run.
- **The CLI:** `scripts/mutate_skeleton.py` runs single-op, `--chain`,
  `--resolve` (author resolution file), `--sample-fill-mock`, and
  `--verify-bundle` modes, derives a collision-safe mutant slug from the
  parent slug and chain signature, and **refuses any `--out-dir` that
  resolves under a `skeletons/` directory** (CR-1: promotion is a PR, never a
  script side effect). WS-8 automation wraps this CLI; it does not reimplement
  it.

### 2.3 The promotion target and its regeneration tooling

`skeletons/<band>/<slug>.json` plus sidecars, scanned by
`generation/skeleton_match.py::_production_candidates` with the shared
`generation/skeleton.py::is_sidecar` predicate
(`SIDECAR_SUFFIXES = (".contract.json", ".lineage.json")`), so a lineage
sidecar landing in a band directory is already invisible to selection
(ADR-020 decision 2, delivered). Zero lineage sidecars exist on disk today:
the first flywheel promotion is also the first production use of the scanner
generalization. A promotion PR additionally regenerates: the catalog document
region (`generation/skeleton_catalog.py::build_catalog_region` between its
BEGIN/END markers in `docs/architecture/story-skeletons.md`) and the skeleton
diagram (`scripts/render_skeleton_diagrams.py`, SHA-verified PlantUML jar with
a graceful `.puml`-only degrade).

### 2.4 The neutralize/parameterize transform for contract-less trees

`scripts/parameterize_skeleton.py` (the production generalization of
`out/pilot/_neutralize.py`, which the plan's WS-8 section names) applies an
agent-authored slotting plan (`beats`/`titles`/`labels` maps) to a pristine
skeleton under six fail-closed checks (coverage, dangling references,
role/words byte-preserved, fingerprint equality, gate not blocked, slot-token
grammar). Its input shape is exactly a promotion bundle's shell, by WS-5
design (WS-5 section 2.4). This is the parameterize-at-promotion path for a
contract-less promoted tree (section 7.3): a WS-5 mutant of a parameterized
parent already ships its contract (stage 4 proved it), so the transform is
needed only for contract-less-parity mutants (Tier-2 parents) and future WS-6
fresh trees.

### 2.5 The measurement instruments (WS-0, delivered)

`diversity/structure.py::structural_distance` and `structure_fingerprint`;
`diversity/aggregate.py::effective_catalog_size` (trend-only, never gates CI
per the WS-0 "never" list); the committed eval panel and
`scripts/run_diversity_eval.py` with its per-PR regression rules. WS-8's
report (section 9) composes these; it adds no new distance, no new judge, and
no CI gate.

### 2.6 What is missing (the WS-8 gap)

Every piece exists; no loop exists. Today the CATALOG escalation terminates in
a log line nobody reads, mutation runs only when a human picks a parent,
operators, and seeds by hand, re-guidance resolution requires a human to write
every seam beat, and promotion requires a human to assemble a PR by hand from
bundle files. The cost per promoted tree is therefore still dominated by human
attention at four points, and the plan's metric (net new trees per month)
rounds to zero. WS-8 removes the human from every point except the one ADR-020
requires: structure approval at the PR.

## 3. Design principles

1. **Wire, do not rebuild.** WS-8 composes delivered surfaces
   (`apply_chain`, `run_chain_acceptance`, `write_bundle`, `verify_bundle`,
   `parameterize_skeleton.py`, `build_catalog_region`, WS-0 distances). Any
   gap is closed by an additive extension in the owning module, never a
   parallel implementation.
2. **Demand-driven, supply-capped.** The loop starts only from a persisted
   saturation reading for a specific cell and stops at hard caps (per-cell,
   global, cool-down; section 8). "Grow with usage" means: no saturation, no
   candidates; saturation, at most a bounded trickle of PRs.
3. **The automation boundary is a file-system and git boundary.** Automation
   writes under `out/` and on non-default git branches, and may open a draft
   PR. Only a human merge writes to `main`'s `skeletons/`. No WS-8 code path
   may push to `main`, enable auto-merge, or approve a PR (section 4.3).
4. **Discard, never weaken** (inherited from WS-5 principle 4). A candidate
   that fails acceptance is logged to the discard ledger and never retried
   with the same signature; no threshold moves. High discard rates tune the
   candidate strategy, never the gate or floors.
5. **Untrusted input never enters the loop as text (OWASP LLM01).** The
   trigger is consumed as enum-valued cell coordinates validated against the
   closed band/length/style vocabularies; no request text, theme brief, or
   family identifier reaches candidate generation. The one LLM touchpoint WS-8
   adds (re-guidance drafting, section 5) consumes catalog content only, and
   its output is untrusted-derived: it passes a deterministic reguide floor,
   the full unchanged acceptance re-run, and human PR review before it can
   exist in the catalog, and it is labeled as agent-authored in the bundle.
6. **Feed-agnostic by contract.** A promotion bundle is a promotion bundle:
   the promotion path (verify, PR prep, review, merge, measure) keys on the
   bundle contract (section 7.1), not on which workstream produced the tree.
7. **Determinism and replayability** (inherited from WS-5 principle 5). Every
   flywheel attempt is a pure function of (parent content hash, chain,
   seeds); the ledger records the signature; any promoted tree re-derives
   byte-for-byte.

## 4. The flywheel loop, end to end

### 4.1 Stage S1: the trigger (WS-4 saturation, persisted as an enum event)

**Extension at the emission site (D1).** `_resolve_skeleton_fill` gains two
fields on the existing log line (`length`, `style`) and, in the same
transaction posture the surrounding code already uses, appends one pipeline
event through `events/writer.py`:

- New `EventType.CELL_SATURATED` with payload allowlist
  `frozenset({"age_band", "length", "style", "level"})`. All four values are
  members of closed enums (`AgeBand`, the length vocabulary, the style
  vocabulary, `DifferentiationLevel`); the writer's allowlist mechanism
  already rejects anything else before write, which is the enforcement of the
  no-free-text rule.

```python
# #ASSUME: data-integrity: PipelineEvent rows anchor to the request whose plan
# escalated, giving the trigger a distinct-request denominator without ever
# recording a family or child identifier in the payload. The payload carries
# ONLY closed-vocabulary enum values (events/writer.py allowlist contract);
# the request anchor is the row's existing foreign key, not payload content.
# #VERIFY: D1 unit test round-trips a CELL_SATURATED event and asserts (a) a
# payload with any extra key or non-enum value is rejected by the writer, and
# (b) the reader (flywheel_scan) drops any row whose values fail enum
# validation instead of propagating them.
```

**The reading interface.** A pure function over the event rows:

```python
@dataclass(frozen=True, slots=True)
class SaturationReading:
    band: str          # validated AgeBand member
    length: str        # validated length member
    style: str         # validated style member
    catalog_events: int      # CATALOG-level events in the window
    leaf_events: int         # LEAF-level events in the window (context only)
    distinct_requests: int   # distinct request anchors behind catalog_events
    window_days: int

def saturated_cells(
    readings: Sequence[SaturationReading],
    *,
    min_catalog_events: int = 3,
    min_distinct_requests: int = 2,
) -> list[SaturationReading]: ...
```

A cell **triggers** when `catalog_events >= 3` within a 30-day window from
`distinct_requests >= 2` (defaults; ratify as OQ-4). The distinct-requests
qualifier keeps one prolific family from single-handedly commissioning
catalog growth; the threshold values are module constants, tunable only by a
reviewed PR (the same posture as the floor baseline).

**LLM01 rule, restated as the trigger's contract:** the flywheel consumes the
saturation signal as a *cell coordinate and counters*, never as theme text.
Nothing about *which theme* saturated the cell reaches candidate generation,
by construction: the event payload cannot carry it (allowlist) and the
strategy (section 6) takes only the cell tuple. Growing the catalog is
theme-agnostic on purpose: a new tree serves every future theme in the cell.

### 4.2 The stage table (interfaces, and where automation stops)

| Stage | What happens | Interface (exact) | Actor |
| --- | --- | --- | --- |
| S1 Trigger | Saturation readings computed per cell from `CELL_SATURATED` events; cells over threshold selected, subject to section 8 caps | D1: `events` writer + `flywheel/trigger.py::saturated_cells`; CLI `scripts/flywheel_scan.py` (read-only report) | Automation |
| S2 Candidate plan | For each triggered cell: eligible parents enumerated, chain templates instantiated, seed budget assigned, ledger-known-dead attempts excluded | D2: `flywheel/strategy.py::plan_attempts(cell, catalog, ledger) -> list[AttemptPlan]` | Automation |
| S3 Generate + accept | Each attempt runs `apply_chain` then `run_chain_acceptance` (the unchanged WS-5 harness); discards append to the ledger | Existing: `mutation/compose.py`; D2 wraps, never modifies | Automation |
| S4 Re-guidance | Held candidates get drafted resolutions (agent), each passing the deterministic reguide floor; acceptance re-runs with `resolved_reguide_ids`; drafts recorded with `author="agent:<model-id>"` | D3: `flywheel/reguide_draft.py` + `generation/templates/reguide_draft.md`; feeds `mutation/reguide.py` unchanged | Automation drafts; human approves later at S6 |
| S5 Bundle | Best surviving candidate per cell (section 6.4 ranking) bundled via `write_bundle`, including sample-fill evidence and diagram | Existing: `scripts/mutate_skeleton.py` end-to-end | Automation |
| S6 PR preparation | `verify_bundle` re-run against live `skeletons/`; shell + contract + lineage copied onto a fresh branch under `skeletons/<band>/`; catalog doc region + diagram regenerated; draft PR opened with the acceptance transcript, reguide before/after table, diagram, and sample-fill evidence in the body; labeled `skeleton-promotion` | D4: `scripts/prepare_promotion_pr.py` | Automation, ending at an OPEN DRAFT PR |
| **S7 Structure approval** | **Review of the diagram, acceptance transcript, lineage, contract diff, and every agent-drafted reguide item; merge or close** | **GitHub PR review; the promotion CI job (D4) independently re-proves gate + contract + floors + verify-bundle on the PR's files** | **Human only. No auto-merge, ever (ADR-020 decision 4)** |
| S8 Close the loop | Merge makes the tree an ordinary catalog skeleton (selection weight 1.0, novelty floor intact); WS-0 metrics and the flywheel report (section 9) record the growth; the cell's saturation counter naturally decays as the new tree absorbs demand | D7: `scripts/flywheel_report.py`; no runtime change | Automation (measurement only) |

### 4.3 The automation boundary (CRITICAL)

Restating ADR-020 decision 4 and WS-5 CR-1 as implementable rules:

1. **Automation may:** read events and the catalog; run mutation, acceptance,
   drafting, bundling under `out/`; create and push a non-default git branch;
   open a **draft** PR labeled `skeleton-promotion`; comment evidence on it.
2. **Automation may never:** write under `skeletons/` on `main` (the CLI
   refusal is inherited; `prepare_promotion_pr.py` writes only inside a
   checkout of its own branch); mark the PR ready-for-review is permitted,
   approving it is not; enable auto-merge on it; merge it; push to `main`;
   modify `floors.py`, the baseline JSON, anything under `validator/`, or the
   caps in section 8.
3. **The PR itself is the human structure-approval instrument** (ADR-020
   decision 4): the reviewer is the owner or a delegated admin, the evidence
   is the bundle's transcript/diagram/sample-fill/lineage, and the review
   explicitly includes every agent-drafted reguide resolution (section 5.4).
4. **Repo enforcement, not just discipline (D4):** the `skeleton-promotion`
   label excludes the PR from any auto-merge tooling (the release workflow's
   auto-merge precedent makes this a real hazard, not a hypothetical); a CI
   job on PRs touching `skeletons/**` re-runs `check_skeleton`,
   `check_theme_contract` (when a contract is present), the anti-clone floor,
   and `verify_bundle`-equivalent lineage/hash validation from scratch, so a
   hand-tampered or stale bundle cannot ride an otherwise-green PR.
5. **Post-merge, safety is unchanged:** every story generated from the
   promoted tree still runs fill -> `run_gate` -> moderation -> ADR-005 human
   story approval. Structure approval and story approval remain two distinct
   human steps, exactly as ADR-020 separates them.

```python
# #CRITICAL: security: the promotion branch preparation is the one WS-8 step
# that writes files destined for skeletons/. It must operate ONLY inside a
# dedicated worktree/checkout of its own feature branch, refuse to run when
# the current branch is main, and re-run verify_bundle IMMEDIATELY before
# copying (a parent changed between bundling and PR prep invalidates the
# acceptance evidence; design 9.2 #EDGE in WS-5).
# #VERIFY: D4 tests: prepare_promotion_pr exits non-zero on branch==main, on
# a verify_bundle mismatch, and on a bundle whose acceptance.json says
# promotable=false or fully_resolved=false; a filesystem sandbox test asserts
# it never writes outside its own worktree.
```

## 5. Re-guidance resolution at scale (the pivotal problem)

### 5.1 Why this is the crux

Every valuable chain emits re-guidance: the ADR-020 evidence exhibit's 2-op
chain emitted 9 items (a graft-seam label, a graft-root entry beat, M2-affected
ending titles and leaf beats). WS-5 D8 closed the loop with *author-supplied*
resolutions, and `mutation/reguide.py` deliberately refuses to generate text.
At flywheel scale, human-authoring ~9 seam texts per candidate is the dominant
cost and the throughput ceiling; leaving it manual makes "grow with usage, not
authoring budget" false in exactly the place it was supposed to be true. Three
options:

### 5.2 The options, analyzed

**(a) Agent-only: an LLM authors the seam guidance, no human reads it before
merge-time review of the whole PR.** Cost: lowest. Safety analysis: the
drafted text becomes beats guidance inside `<<FILL ...>>` bodies, which means
it re-enters *every future fill prompt* for stories from this tree; it is
untrusted-derived prompt material (plan safety invariant 4). Mitigations that
exist regardless: the drafting inputs are catalog content only (the parent's
surrounding beats, the emitted item's `current_text`, the contract's slot
meanings), never request text; the resolved shell must re-pass the full gate,
the anti-clone floor, and the sample fill; every story later filled from it
faces the fill gate, fidelity review, moderation, and ADR-005. Residual risk:
guidance *quality* (an awkward seam yields awkward stories) and subtle
tone/content drift below classifier thresholds, with no human having read the
seam text as such (the PR reviewer would see it only if they dig into the
JSON). Verdict: the safety floor holds, but it wastes the one human review the
process already requires.

**(b) Human-only (status quo).** Cost: highest; the throughput ceiling.
Safety: maximal. Verdict: correct fallback, wrong default; it re-creates the
authoring-budget dependence WS-8 exists to remove, for a surface (seam beats)
that is a fraction of a tree.

**(c) Hybrid: the agent drafts, the deterministic reguide floor screens, and
the human approves each draft inside the same PR review that ADR-020 already
mandates.** Cost: near (a); the marginal human cost is reading ~9 short
before/after pairs, rendered as a table in the PR body (D4), inside a review
the human is performing anyway. Safety: (a)'s mechanical floor plus a human
actually reading every drafted seam before it can exist on `main`. The
`ResolvedReguide.author` field records `agent:<model-id>` so the audit trail
distinguishes drafted from hand-authored resolutions forever, and the reviewer
may overwrite any draft in the PR (it is a text field in a JSON file on a
branch).

**Recommendation: (c), ratify as OQ-1.** It converts the ADR-020 review from
a rubber-stampable formality into the exact control point the drafted content
needs, at zero added process.

### 5.3 The deterministic reguide floor (D3)

Every drafted resolution must pass, before it is written into the resolution
file (fail = the item stays unresolved and the candidate stays held):

1. **Surface parity.** For a NODE target: substituting the drafted beats into
   the FILL body still parses under the FILL grammar with `role=` and
   `words=` byte-identical to the pre-mutation values (the same invariant
   `parameterize_skeleton.py` check 3 enforces). For a CHOICE/ENDING target:
   single line, and the label keeps the frozen action-semantic obligation in
   scope for the human check (mechanically unverifiable; flagged in the PR
   table).
2. **Slot-token discipline.** `{TOKEN}`s in the drafted text must be a subset
   of the mutant contract's declared slot ids (no invented slots; no dropped
   mandatory coverage, re-proven by stage 4 contract acceptance on the re-run
   anyway); for contract-less mutants, zero `{`/`}` characters.
3. **Structural injection block.** No `<<`/`>>`, no fence-marker strings, no
   control characters, printable charset, no U+2014 and no U+2013; length
   capped (beats <= 600 characters, labels/titles <= 120), reusing the
   exported `validator/slots.py` structural helpers where they fit rather
   than copying them.
4. **Band vocabulary floor.** The band-mandatory denylist bundles
   (`band_mandatory_bundles`) stem-matched against the drafted text; a hit
   fails the draft. Stricter than strictly necessary (the gate and moderation
   re-check downstream) and deliberately so: drafted guidance should never
   need the downstream net.
5. **Determinism of acceptance.** After resolution, `run_chain_acceptance`
   re-runs in full with `resolved_reguide_ids`; only a `promotable=true`
   result proceeds to bundling. The floor never marks anything resolved by
   itself; it only refuses drafts.

```python
# #CRITICAL: security: the drafting prompt consumes catalog content only
# (parent beats, item current_text, contract slot meanings) and the mutant
# cell enums; no request text, brief, family, or child artifact may be an
# input, transitively. The drafted output is untrusted-derived (LLM01): it is
# fenced as data if ever re-prompted, floor-screened before persistence, and
# faces the full acceptance re-run plus human PR review before touching main.
# #VERIFY: D3 grep-style test (mirroring WS-1 exit criterion 5 and WS-5 CR-5):
# flywheel/ imports nothing from story_requests/ and no drafting function
# accepts a brief or premise; unit tests pin every floor rule with a
# violating fixture (invented slot token, fence marker, denylist stem,
# words= drift) and assert the item stays unresolved.
```

### 5.4 What the human sees (the S7 contract)

The PR body renders `reguide.json` as a table: target, reason, before,
drafted-after, author. The review checklist (committed as part of D4's PR
template for `skeleton-promotion` PRs) requires the reviewer to check a box
per drafted item. The `mutation/reguide.py` docstring is amended (D3) from
"never generates guidance text" to "resolution text is author-attributed;
agent-drafted resolutions are floor-screened untrusted-derived content that
MUST be human-reviewed in the promotion PR", keeping the module's own code
generation-free (drafting lives in `flywheel/`, feeding `ResolvedReguide`
values in).

## 6. Candidate strategy per saturated cell

### 6.1 Parent eligibility (precedence-ordered filter)

From the triggered cell's catalog (the same discovery
`floors.load_in_cell_catalog` uses), keep parents that are, in order:

1. `production_eligible` (never the MVP seeds);
2. `metadata.series is None` (WS-5 operator precondition, inherited);
3. within lineage depth: a parent whose own `*.lineage.json` sidecar exists is
   generation >= 1; v1 requires parent generation <= 1, so no tree is ever
   more than two derivations from a hand-authored root (recommendation;
   OQ-5). Depth is computed by walking lineage sidecars on disk, no new
   metadata;
4. not the parent of an already-open `skeleton-promotion` PR for this cell
   (section 8's one-PR-per-cell cap makes this mostly moot, kept as a
   belt-and-braces check).

### 6.2 Chain templates (what to attempt, in value order)

Fixed, versioned templates in `flywheel/strategy.py`, instantiated per parent;
all bounded by `MAX_CHAIN_LENGTH = 3` (OQ-7, ratified in WS-5):

| Template | Chain | Applies to | Rationale |
| --- | --- | --- | --- |
| T1 | M3 graft (same-band donor) -> M2 re-map | Tier-1 parents with an eligible donor | The proven highest-value pairing (ADR-020 evidence exhibit: distance 0.3362 >= TAU_STRUCT) |
| T2 | M1 swap -> M2 re-map | Tier-1 parents with two swappable closed subtrees | Cheapest structural pairing; M1 alone preserves aggregate features, M2 decouples outcomes |
| T3 | M4 insert-decision -> M1 swap -> M2 re-map | Tier-1 parents under the cell node envelope max | The 3-op reach when T1/T2 seeds fall short of TAU_STRUCT |
| T4 | M5a retune + M5b gate/rewire (chain of 2) | Tier-2 parents | State-only growth for the 12 stateful trees; judged by TAU_STATE, not TAU_STRUCT |

Donor selection for T1: same band, `production_eligible`, non-series, and
maximum `structural_distance` from the host among eligible donors (a distant
donor imports genuinely different material, which is what pushes the composed
result over the floor).

### 6.3 Attempt budget and the discard ledger

Per triggered cell per cycle: at most `MAX_ATTEMPTS_PER_CELL = 12` acceptance
runs (for example 3 templates x 4 seeds, or fewer templates with more seeds
where preconditions filter parents). Attempts are cheap (preconditions gate
free, gate runs are sub-second, the Tier-2 walk is the only costly stage and
only T4 pays it), but the budget exists so a pathological cell cannot burn a
cycle.

**The ledger (D2):** `out/mutations/_ledger/attempts.jsonl`, append-only, one
record per attempt:
`{attempt_sig, parent_slug, parent_sha256, cell, chain: [(op, params, seed)],
outcome: promotable|held|discarded, failing_stage, discard_reason, distances,
timestamp}` where `attempt_sig = sha256(parent_sha256 + canonical chain
JSON)`. The strategy skips any planned attempt whose `attempt_sig` already has
an outcome: operators are deterministic, so re-running a known-dead signature
provably reproduces the discard. A parent content change changes
`parent_sha256`, which correctly invalidates the memory for that parent.

```python
# #EDGE: external-resources: the ledger lives under gitignored out/, so a
# fresh checkout loses it. Acceptable by design: determinism means a lost
# ledger costs only recomputation, never correctness, and committing per-
# attempt records would spam git history (OQ-7 asks whether to commit it).
# #VERIFY: D2 test: a ledger round-trip skips a recorded signature; deleting
# the ledger and re-running reproduces byte-identical outcomes for the same
# (parent_sha256, chain) signatures.
```

### 6.4 Ranking and selection (precedence rules)

Among the cycle's surviving candidates for a cell (promotable, or held with
all reguide items successfully drafted and re-accepted), pick **one** to
bundle and PR (per the section 8 cap), by precedence:

1. Larger `min over in-cell siblings of structural_distance(s, candidate)`
   (headroom above `TAU_CELL`: prefer the candidate least like *anything*
   already in the cell; this is the flywheel's own anti-near-duplicate
   preference layered above the floor);
2. then larger `structural_distance(parent, candidate)` (for T4: larger state
   signature distance);
3. then fewer re-guidance items (cheaper review);
4. then the lower seed (a deterministic tiebreak).

Non-selected survivors are recorded in the ledger as `outcome: shelved` and
are naturally reconsidered next cycle at zero regeneration cost (same
signature, known outcome, bundle re-derivable).

### 6.5 Catalog hygiene (the TAU_CELL clamp lesson)

The floor baseline's clamp note is a standing warning: the hand-authored
catalog already contains one near-identical in-cell pair (distance 0.000947),
which is exactly the failure mode a careless flywheel would mass-produce. Two
responses, both in this design: (a) the anti-clone floor plus the section 6.4
rank-by-headroom preference mean the flywheel structurally cannot add a
near-duplicate and actively prefers distinctness; (b) the flywheel report
(section 9) includes a standing "in-cell minimum pairwise distance" table over
the WHOLE catalog, so the pre-existing pair and any future erosion is visible
to the owner every cycle. Automation reports; the owner decides whether the
legacy pair warrants curation. No automated deletion, ever.

## 7. Feed-agnostic promotion

### 7.1 The promotion-bundle contract (normative)

A promotion bundle is a directory containing, exactly as `bundle.write_bundle`
already lays out: the gate-passing shell `<slug>.json`; `<slug>.lineage.json`
(section 7.2); `acceptance.json` with `promotable: true` and a full stage
transcript; `reguide.json` with `fully_resolved: true`; `<slug>.contract.json`
when the tree is parameterized; `sample-fill/` evidence; a diagram. The
promotion path (S6-S8) consumes ONLY this contract: `prepare_promotion_pr.py`
takes a bundle directory, verifies it, and prepares the PR without knowing or
caring which workstream produced the tree. WS-5's CLI already emits it; WS-6
must emit it; a future composer must emit it.

### 7.2 Lineage v2: the origin discriminator (D5)

`Lineage` v1 requires `parent_slug` and a non-empty `op_chain`, which a WS-6
fresh tree cannot honestly supply. D5 bumps `LINEAGE_VERSION` to 2, keeping v1
readable (the reader keys on `lineage_version`, per the module's own
contract):

```python
class LineageV2(BaseModel):
    lineage_version: int          # 2
    origin: Literal["mutation", "fresh", "composed"]
    mutant_slug: str
    # origin == "mutation": exactly the v1 fields
    parent_slug: str | None
    parent_sha256: str | None
    donor_slugs: list[str]
    op_chain: list[OpChainEntry]  # empty permitted only for origin != "mutation"
    # origin == "fresh" (WS-6): the generation provenance instead
    generator: str | None         # e.g. "ws6:<pipeline-version>"
    generation_params_sha256: str | None
    created_at: str
    tool_version: str
    acceptance_digest: str
```

Cross-field validators enforce the origin-specific requirements (a
`mutation` record must carry parent fields and a non-empty chain, byte-
compatible with v1 semantics; a `fresh` record must carry generator fields and
no parent). `verify_bundle` gains an origin branch: `mutation` verifies the
parent hash as today; `fresh` verifies the acceptance digest only (there is no
parent to go stale, but the transcript must match). Acceptance for parentless
candidates reuses the existing ladder with the parent-relative clauses
inapplicable: the gate, cell assertion (against the declared target cell, not
an inherited one), Tier-2 checks, and the in-cell `TAU_CELL` clause all apply;
the fingerprint-vs-parent and `TAU_STRUCT` clauses are vacuous without a
parent. The exact WS-6 acceptance entry point is specified when WS-6 is
designed; D5's obligation is only that the bundle and lineage contracts do not
have to change again for it.

### 7.3 Parameterize-at-promotion (the neutralize path)

A contract-less promoted tree (a Tier-2-parity mutant today; a WS-6 fresh tree
later) may be parameterized at promotion using the WS-2 recipe verbatim: an
agent authors a slotting plan, `scripts/parameterize_skeleton.py` applies it
under its six fail-closed checks, a contract is authored, and
`scripts/check_theme_contract.py` accepts. Recommendation (OQ-6): promotion
does NOT block on parameterization. Rationale: ADR-020 decision 6 already
accepts contract-less parity (a contract-less mutant is exactly as safe as its
contract-less parent, same free-text fill path, same gate), the WS-2 Tier-2
migration wave is the scheduled home for closing that gap, and coupling two
reviewed transforms into one PR doubles the review surface per promotion. A
tree promoted contract-less simply joins that wave.

## 8. Scheduling, cadence, and bounds

### 8.1 Cadence: manual-first, then periodic (OQ-2)

- **v1 (D1-D4): operator-driven.** `scripts/flywheel_scan.py` prints the
  saturation report; the owner runs `flywheel_candidates` for chosen cells and
  `prepare_promotion_pr.py` for the winner. Every stage is automated
  internally, but a human presses each button. This exercises the whole loop
  and the review workflow before any scheduler exists, exactly the
  cheapest-and-safest-first posture WS-5 used (one manual promotion before any
  automation).
- **v2 (D8): periodic.** A scheduled run (weekly; a nox session invoked by an
  operator cron or a scheduled workflow, environment-dependent since S1 needs
  database read access) executes S1-S6 within the caps below and stops at
  draft PRs. No event-driven per-request triggering: saturation is a
  slow-moving 30-day aggregate and weekly is faster than review capacity
  anyway.

### 8.2 Hard bounds (the operationalization of "grow with usage")

| Bound | Default | Purpose |
| --- | --- | --- |
| Trigger threshold | 3 CATALOG events / 30 days / >= 2 distinct requests | No demand, no growth (section 4.1, OQ-4) |
| `MAX_ATTEMPTS_PER_CELL` per cycle | 12 | Compute and log hygiene (section 6.3) |
| Open `skeleton-promotion` PRs per cell | 1 | The reviewer compares one candidate against one cell at a time; a second candidate for the same cell waits |
| Open `skeleton-promotion` PRs global | 3 | Review-queue protection: the flywheel must never flood the one human it depends on |
| Per-cell cool-down after a merge | 30 days | Let WS-0 metrics and real selection absorb the new tree before growing the same cell again |
| Monthly promotion budget | 4 merged trees | Matches the metric's unit (net new trees per month) and keeps contract-maintenance growth (ADR-020 accepted cost) deliberate |

All six are constants in `flywheel/strategy.py`, changed only by reviewed PR.
When a bound blocks a triggered cell, the scan report says so explicitly
(`"cell X saturated but capped: <bound>"`), so demand pressure is never
silently dropped, only deferred.

## 9. Metrics and observability

All computed from existing instruments; trend-only, never a CI gate (the WS-0
"never" list applies).

- **Net new trees per month (the headline):** merged `skeleton-promotion` PRs,
  derived from `*.lineage.json` additions in `skeletons/**` git history plus
  the catalog scan; hand-authored additions are counted separately (no
  lineage sidecar) so the flywheel's contribution is honest.
- **Distinct trees per cell (trend):** per cell, the skeleton count and the
  in-cell pairwise `structural_distance` distribution (min/median), the same
  numbers the floor calibrator computes; a rising count with a collapsing
  minimum distance would be the flywheel gaming its own metric, and the
  report surfaces both together on purpose.
- **Effective catalog size:** `diversity.aggregate.effective_catalog_size`
  over the served window, unchanged.
- **Promotion funnel:** per cycle from the ledger: attempts, discards by
  stage (the discard-rate economics WS-5 flagged), held, drafted-resolved,
  shelved, bundled, PR opened, merged, closed-without-merge. Promotion
  acceptance rate = merged / PRs opened.
- **Re-guidance cost:** items per bundled candidate; agent-draft floor-pass
  rate; human edit rate at review (drafts overwritten in the PR before merge,
  measurable from the PR diff vs the bundle's reguide.json). This is the
  evidence OQ-1's ratification asks to be re-checked against after the first
  promotions.
- **Demand response:** per triggered cell, CATALOG-event rate before vs after
  a merge (does growing the cell actually relieve saturation; if not, the
  trigger threshold or the escalation ladder needs revisiting, and the report
  is where that shows up).

Shape: `scripts/flywheel_report.py` emits a markdown report (committed under
`docs/planning/flywheel-reports/` per run or attached to the cycle's PRs;
OQ-8) with the six tables above; `run_diversity_eval.py` is not modified.

## 10. Safety-invariant mapping (plan section 7)

| Invariant | How WS-8 upholds it |
| --- | --- |
| **7.1** The frozen safety object is the ADR-011 constraint grammar, enforced by the gate on every tree and fill. | WS-8 creates no tree except through WS-5 operators (grammar-precondition-checked) or, later, WS-6 candidates, and every one passes the byte-identical `run_gate` inside the unchanged acceptance harness (S3) plus the promotion CI re-proof (S7). No WS-8 module imports anything from `validator/` except to call it; the floors, thresholds, and caps it adds are all reject-only or supply-limiting. |
| **7.2** Every generated story passes the full gate and moderation before publish. No novelty exception. | Doubly inherited: the promoted shell passed the full gate at acceptance and re-passes at every `load_skeleton`; every story filled from it runs the untouched fill -> gate -> moderation -> ADR-005 chain. The WS-8 additions (trigger thresholds, reguide floor, ranking, caps) can only prevent or defer a promotion, never exempt one. ADR-020 decision 3 restated: composed and fresh trees inherit the same bar via the section 7 contract. |
| **7.3** Per-band content guarantees (K13) are enforced by structure + gate, never by trusting a brief. | The flywheel is theme-blind by construction (section 4.1): no brief exists in the loop. Contracts ride the WS-5 stage-4 acceptance with the band-mandatory floor unioned in regardless of contract content; the reguide floor adds a band-denylist screen on drafted guidance (5.3 rule 4), stricter-only. |
| **7.4** LLM01 covers derived artifacts; fence at every reuse. | The two derived-content surfaces are (1) the saturation signal, consumed as allowlisted enum coordinates that structurally cannot carry text (4.1), and (2) agent-drafted reguide text, which is labeled untrusted-derived, floor-screened, re-accepted by the full harness, human-reviewed per item in the PR, and, once merged, becomes beats guidance that re-enters prompts only through the existing fenced fill pipeline (5.3 #CRITICAL). The drafting prompt itself consumes catalog content only. |
| **7.5** Novelty floor: selection never fully excludes an eligible option. | Untouched: `skeleton_match.py` is not modified, promoted trees enter at weight 1.0, and the complementary direction is strengthened, not weakened: the anti-clone floor plus the 6.4 headroom ranking and the 6.5 hygiene report keep "new tree" meaning genuinely new, so the novelty the floor protects is real. |

## 11. What does not change

- `validator/`, `moderation/`, `publishing/`, ADR-005 approval: no rule,
  threshold, cap, or severity is edited.
- `mutation/` operators, `acceptance.py`'s ladder, `floors.py` values and the
  committed baseline, `compose.py`'s bound, `scripts/mutate_skeleton.py`'s
  refusal semantics. (Additive only: Lineage v2 in `bundle.py` (D5), the
  reguide docstring amendment (D3).)
- `generation/skeleton_match.py`: weights, novelty floor, sidecar skip.
- The WS-2 contract format, slot validator, render post-conditions;
  `scripts/parameterize_skeleton.py` (consumed as-is in 7.3).
- `skeletons/**` on `main`: changed exclusively by human-merged PRs.
- The WS-4 escalation ladder and the `3x` similarity penalty (the trigger
  reads the ladder's output; it does not tune it).

## 12. Deliverables

Ordered cheapest-and-safest first; each independently landable and reviewable;
D1-D4 are the manual-loop v1, D5-D8 the scale-out.

- **D1. Trigger persistence + scan** (`events/models.py` + `events/writer.py`
  allowlist entry, the two log fields in `authoring_plan.py`, new pure
  `src/cyo_adventure/flywheel/trigger.py`, CLI `scripts/flywheel_scan.py`,
  read-only). **Tests:** allowlist rejection of extra/non-enum payload keys;
  enum re-validation on read drops junk rows; threshold math on hand-built
  readings; the log-field pin. **Safety property:** the trigger surface
  structurally cannot carry free text (writer allowlist + reader enum
  validation, both directions tested).
- **D2. Candidate strategy + ledger** (`flywheel/strategy.py`: parent
  eligibility filter incl. lineage-depth walk, chain templates T1-T4, donor
  pick, attempt budget, `attempt_sig` ledger, 6.4 ranking; CLI
  `scripts/flywheel_candidates.py` wrapping `apply_chain` +
  `run_chain_acceptance` + the existing bundle writer). **Tests:** template
  instantiation over the real catalog; ledger skip/replay determinism;
  ranking precedence on fixtures; series/MVP/depth exclusions. **Safety
  property:** strategy inputs are catalog files and cell enums only (grep
  test: `flywheel/` imports nothing from `story_requests/`; no function
  accepts a brief).
- **D3. Re-guidance drafting + floor** (`flywheel/reguide_draft.py`,
  `generation/templates/reguide_draft.md`, the deterministic floor of 5.3,
  the `reguide.py` docstring amendment, `author="agent:<model-id>"`
  attribution; acceptance re-run wiring). Behind OQ-1's ratification; ships
  with a `--no-draft` mode so the manual path survives. **Tests:** every
  floor rule with a violating fixture; a drafted resolution set drives a held
  candidate to promotable via the UNCHANGED harness; attribution round-trips
  into `reguide.json`. **Safety property:** no drafting code path can mark an
  item resolved without the floor passing, and the drafting provider call
  carries no request-derived content (5.3 #CRITICAL's #VERIFY).
- **D4. Promotion-PR preparation + repo enforcement**
  (`scripts/prepare_promotion_pr.py`: fresh `verify_bundle`, worktree-only
  writes, branch refusal on `main`, catalog doc region + diagram regen, PR
  body with transcript and the 5.4 reguide table, `skeleton-promotion` label,
  draft PR; the PR-template checklist; the CI job on `skeletons/**` PRs
  re-running check_skeleton + contract + floors + lineage/hash validation;
  auto-merge exclusion for the label). **Tests:** the 4.3 #VERIFY set;
  CI-job fixture PRs (valid bundle passes, tampered shell fails, stale parent
  fails, missing lineage fails). **Safety property:** automation ends at a
  draft PR; nothing in D4 can merge, approve, or write `skeletons/` on
  `main`. One end-to-end manual-loop promotion (D1-D4, a real saturated cell
  or a staged one) is D4's exit criterion, mirroring WS-5 D8's evidence
  posture.
- **D5. Feed-agnostic contract v2** (`bundle.py`: LineageV2 with the origin
  discriminator and cross-field validators, v1 read-compat, `verify_bundle`
  origin branch; the written feed-contract note in this doc's section 7
  referenced from the WS-6 plan section). **Tests:** v1 bundles still verify;
  a `fresh` record without generator fields fails validation; a `mutation`
  record without a parent fails. **Safety property:** no origin value relaxes
  any acceptance stage that applies to it (the in-cell clone clause and gate
  apply to every origin).
- **D6. Parameterize-at-promotion glue** (runbook + script glue chaining
  `parameterize_skeleton.py` -> contract authoring -> `check_theme_contract.py`
  for a contract-less bundle, as an optional second PR after promotion, per
  OQ-6's recommendation). **Tests:** the chained checks on a fixture bundle.
  **Safety property:** the transform's six fail-closed checks are the
  gatekeeper; the glue adds no bypass.
- **D7. Metrics + the flywheel report** (`scripts/flywheel_report.py`: the
  six section 9 tables from git history, the catalog, WS-0 functions, and the
  ledger; includes the 6.5 hygiene table). **Tests:** report determinism on a
  fixture repo/ledger; the lineage-vs-hand-authored attribution split.
  **Safety property:** read-only everywhere; never gates CI.
- **D8. Scheduled cadence + docs** (the periodic S1-S6 runner with the
  section 8.2 caps and cool-downs, behind OQ-2; update
  `story-flexibility-plan.md` WS-8 status, `capability-register.md` K3 note,
  the ADR-020 "WS-8 automation, when built, prepares PRs" consequence with a
  delivered pointer, and `docs/template_feedback.md` if any template gap
  surfaces, none identified by this design). **Tests:** cap and cool-down
  enforcement on simulated event streams (a flood of saturation events yields
  at most the capped PR count). **Safety property:** every bound of 8.2 is
  enforced in one place and a capped cell is reported, never silently
  dropped.

Sizing: D1-D2 are the first implementer unit (the trigger and the strategy,
pure code plus two CLIs); D3 the second (the one LLM touchpoint, isolated);
D4 the third (git/PR machinery plus CI, ending in the evidence promotion);
D5-D6 a fourth (contract work); D7-D8 the fifth. Each unit lands green on the
standard quality gates before the next starts.

## 13. Testing strategy

Unit (no network, no live DB, per the `tests/` posture; the flywheel is
designed so only D1's writer touch and D8's runner need DB fixtures):

- Property tests over the real catalog corpus: for every triggered-cell
  simulation, every strategy-planned attempt signature is deterministic and
  ledger-replayable; every D2-selected candidate satisfies the 6.4 precedence
  ordering (pinned by pairwise comparison).
- Discard-path coverage: every stage of the S1-S6 pipeline has a pinned
  refusing fixture (unsaturated cell, capped cell, exhausted budget, all
  attempts discarded, draft floor failure, stale bundle, tampered shell,
  branch==main).
- The LLM01 pins: the D1 allowlist both-directions test, the D2/D3 grep
  tests (no `story_requests` import, no brief-accepting signature), the D3
  floor fixtures, and a template test that `reguide_draft.md` fences its
  catalog-content inputs as data.
- The automation-boundary pins: `prepare_promotion_pr.py` sandbox tests
  (writes only inside its worktree, exits non-zero on every 4.3 refusal), a
  repo-config test that the `skeleton-promotion` label is excluded from
  auto-merge tooling, and the D4 CI job's fixture PRs.
- Mutation-testing candidates (mutmut): the trigger threshold math, the
  ledger signature, the 6.4 ranking comparator, the reguide floor rules.
- Coverage: >= 80% overall, near-100% for `flywheel/trigger.py`,
  `flywheel/strategy.py`, and the reguide floor (the decision-bearing pure
  core). Quality gates: BasedPyright strict, Ruff, Bandit, pre-commit, signed
  Conventional Commits, no U+2014 or U+2013 anywhere including templates,
  report strings, and PR-body text.

Integration: the D4 end-to-end (scan -> candidates -> draft -> bundle ->
verify -> PR-prep dry run against a temp copy of `skeletons/`) as a
nox-runnable script; D8's cap simulation. The promoted tree's fill path is
covered by existing worker/orchestrator suites automatically once merged (no
new runtime seam, by design).

## 14. Risks and critical-review items

**CR-1 (blocking). Automation prepares PRs, humans merge them.** No WS-8 code
path may write `skeletons/` on `main`, approve, enable auto-merge on, or merge
a `skeleton-promotion` PR; the label is excluded from auto-merge tooling and
the D4 CI job independently re-proves every promotion PR. (ADR-020 decision 4;
WS-5 CR-1 inherited verbatim.)

**CR-2 (blocking). Reject-only, discard-only.** The acceptance harness,
floors, and gate are consumed unchanged; every WS-8 addition (trigger
thresholds, reguide floor, ranking, caps) can prevent or defer a promotion but
never admit, exempt, or retry-by-loosening. No WS-8 module imports `validator/`
except to call it.

**CR-3 (blocking, LLM01). The trigger is enums, the draft is fenced.** The
saturation event payload is allowlist-enforced enum-only in both write and
read directions; no request text, brief, theme, family, or child artifact
enters `flywheel/` transitively; agent-drafted reguide text is
untrusted-derived, floor-screened, attribution-labeled, re-accepted by the
full harness, and human-reviewed per item before merge.

**CR-4 (blocking). Staleness is a hard failure.** `verify_bundle` (or its
origin-aware v2) must pass immediately before PR preparation AND again in the
promotion CI job; a parent changed after bundling, a missing lineage, or an
acceptance transcript that does not match the shipped files fails the PR.

**CR-5 (blocking). The metric cannot be gamed by the thing it measures.** The
distinct-trees count is reported only alongside the in-cell distance
distribution (section 9), the anti-clone floor is blocking at promotion, and
the 6.4 ranking prefers headroom; a rising count with collapsing distances is
surfaced, not celebrated.

Risks (non-blocking):

1. **Draft quality** is the residual editorial surface (WS-5 risk 1, now at
   scale). Bounded by the reguide floor, the sample fill, fill-time fidelity,
   and the per-item human check; measured by the D7 edit-rate metric, which is
   the designated evidence for revisiting OQ-1.
2. **Review-queue fatigue.** Even 3 open PRs of ~100-node trees is real work.
   Mitigated by the bundle's diagram/transcript/sample-fill (built for cheap
   review), the caps, and the one-per-cell rule; if fatigue persists, the
   in-app surface deferred by ADR-020 becomes the follow-up, not a loosened
   review.
3. **Trigger sensitivity.** The 3-events/2-requests threshold is a guess;
   too low floods, too high starves. Tunable constants plus the D7
   demand-response table exist exactly to calibrate it (OQ-4).
4. **Template exhaustion.** Four chain templates over a small in-cell parent
   set may run dry (all signatures ledgered) while a cell stays saturated.
   The scan reports "cell saturated, strategy exhausted", which is precisely
   the evidence the plan needs to prioritize WS-6 (fresh trees) or the
   composer; the flywheel degrades to a signal, never to a weakened floor.
5. **Generational drift** (mutant-of-mutant chains diverging from
   human-authored guidance). Capped at depth 1 parents in v1 (OQ-5); the
   lineage sidecars make depth computable forever, so the cap can be lifted
   with evidence.
6. **Scheduler environment coupling.** D8's runner needs DB read access and
   git push credentials in one place; environment-specific and deliberately
   last. The manual v1 loop has no such coupling.

## 15. Open questions for sign-off

Each with a recommendation; all are ratification items for the supervisor
review. OQ-1 and OQ-2 are the decisions the requester specifically asked to be
confirmed.

- **OQ-1 (PIVOTAL: re-guidance at scale).** Agent-only drafting (a),
  human-only authoring (b), or hybrid agent-draft with deterministic floor
  plus per-item human approval inside the promotion PR (c), per section 5.
  **Recommendation: (c) hybrid.** It removes the throughput ceiling while
  spending the human review ADR-020 already mandates on exactly the content
  that needs it; the D7 edit-rate metric is the designated evidence for
  tightening or relaxing later. Ratifying (c) also ratifies the
  `reguide.py` docstring amendment (D3) and the `author` attribution rule.
- **OQ-2 (cadence and boundary).** Manual-first (operator runs each stage via
  CLI, D1-D4) then a weekly scheduled S1-S6 run behind the section 8.2 caps
  (D8), with automation always ending at a draft PR. **Recommendation:
  ratify exactly this**, including the six cap defaults (3 events/30
  days/2 requests; 12 attempts; 1 PR per cell; 3 global; 30-day cool-down;
  4 merges per month) as reviewed-PR-only constants.
- **OQ-3 (wait for WS-6?).** Build the WS-5-mutant-only flywheel now and
  integrate WS-6 later through the D5 feed contract, or block WS-8 on WS-6.
  **Recommendation: mutant-only first.** Three of four inputs are delivered;
  the feed contract (section 7) makes WS-6 a plug-in, not a rework; and the
  flywheel's own exhaustion signal (risk 4) is the best evidence for when
  WS-6 is actually needed and for which cells.
- **OQ-4 (trigger threshold values).** Ratify 3 CATALOG events per 30 days
  from >= 2 distinct requests as the trigger default. **Recommendation: yes,
  as tunable constants**, recalibrated against the D7 demand-response table
  after the first quarter.
- **OQ-5 (lineage depth).** Restrict flywheel parents to generation <= 1
  (promoted mutants may parent once; grandchildren may not parent) in v1.
  **Recommendation: yes.** Guidance quality decays with derivation distance
  from a human author; lift with edit-rate and fidelity evidence via an
  ADR-020 amendment note, not silently.
- **OQ-6 (parameterize-at-promotion posture).** Optional follow-up per tree
  (this design, section 7.3) vs mandatory contract at every promotion.
  **Recommendation: optional.** ADR-020 decision 6's parity rule already
  covers the safety question; mandatory coupling doubles per-promotion review
  for no gate-relevant gain, and the WS-2 Tier-2 wave is the scheduled
  closure.
- **OQ-7 (ledger placement).** Local gitignored `out/mutations/_ledger/`
  (this design) vs a committed ledger. **Recommendation: local.** Determinism
  makes ledger loss harmless (recompute), and per-attempt records would spam
  history; revisit only if D8's scheduled runs land on ephemeral
  environments where recomputation is measurably wasteful.
- **OQ-8 (report placement).** Commit cycle reports under
  `docs/planning/flywheel-reports/` vs attach to the cycle's PRs only.
  **Recommendation: commit them.** The trend tables (hygiene, demand
  response) are longitudinal and belong in versioned history; a PR attachment
  dies with the PR tab.
