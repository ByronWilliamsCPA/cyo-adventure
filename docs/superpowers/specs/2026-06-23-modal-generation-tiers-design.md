---
title: "Skeleton-Library Story Generation with Tiered Backends (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "docs/planning/research/cyoa-research-reconciliation.md, commercial-cyoa-graph-theory-handoff.md; OpenRouter roleplay-category usage data; Modal auto-endpoints docs"
purpose: "Design for pre-authored skeleton-library story generation with reading-level-routed tiered backends: Modal auto-endpoints, OpenRouter fallback, local Ollama, and an offline Opus-via-Claude-Code authoring skill."
tags:
  - planning
  - architecture
  - project
---

> Branch: `feat/modal-generation-tiers` | Date: 2026-06-23 | Author: Byron Williams (with Claude)
> Supersedes the chunked-generation draft of the same date.
> Research basis: `commercial-cyoa-graph-theory-handoff.md` (JHM primary) and
> `cyoa-research-reconciliation.md` (four sources cross-checked).

## 1. Problem

Phase 2b live generation has the model design the story graph and write the prose
in one pass. The model-designed graph is the dominant failure source: every yield
blocker (dangling refs, orphan nodes, node-count, depth, reachability, the
orphan-DELETE repair loop) is *structural*. First live yield was ~30%.

Two backends exist, each with a disqualifying weakness:

- **OpenRouter** (`anthropic/claude-haiku-4.5`): reliable, but ~$2-3.5/story and
  only ~30% yield without more work.
- **Local homelab Ollama**: $0, but 64+ min/story, currently TLS-blocked, and
  small models fail the structural gates.

Separately, commercial CYOA has a known shape the current budgets do not target.
Four cross-checked sources converge: classic kids' CYOA is **short, shallow, and
binary; its ~20 endings come from many short reconvergent leaves, not deep trees;
and age rises by escalating theme and tone, not branch depth.** Endings and
decisions are the two structural properties that drive both reader ratings and
sales, exactly what a yield-optimizing generator sheds first.

We also have two under-used assets: **$30/month of Modal credits** (use-it-or-lose
it) and **Claude subscription capacity** usable from within Claude Code.

## 2. Core Decision: Pre-Authored Skeletons, Model Fills Prose

Separate **structure** from **prose**. Maintain a library of pre-authored,
pre-validated **skeletons** (abstract story graphs with empty prose slots),
organized in a matrix of **reading level x length x topology**. To generate a
story, select a skeleton for the requested (theme, reading level, length),
tracking coverage for variety, then hand the fixed graph to a model and have it
fill *only* the prose to fit the framework.

Why this is the right architecture:

- **It deletes the failure class.** The model never emits an invalid graph because
  it never emits a graph. Structural gates become invariants that pass by
  construction.
- **A skeleton is a pre-validated Storybook with empty prose**, so the existing
  schema ([models.py](../../../src/cyo_adventure/storybook/models.py)) and validator
  ([layer1.py](../../../src/cyo_adventure/validator/layer1.py)) validate it once at
  authoring time. At generation, only the *filled prose* is re-checked against
  content and reading-level gates.
- **It guarantees the commercial metrics.** Endings and decisions become authored
  properties of the skeleton, not emergent behavior a yield loop erodes. The genre
  achieves many endings through **short reconvergent leaves**, which the skeleton
  encodes deliberately.
- **Fill is embarrassingly parallel** given the skeleton; node prose is generated
  in batches, cheaply and fast.
- **It makes stateful coherence tractable.** Because the graph and state rules are
  fixed before any prose exists, the reachable state at each node is computable and
  handed to the model as fill context, instead of asking the model to invent
  structure and track state at once.
- **Node count decouples from model ability.** Genre-faithful sizes (e.g. ~45 short
  nodes for a young story) are authored into the skeleton; the model only fills
  short beats, regardless of the graph size a model would naturally produce.

## 3. The Matrix: Reading Level x Topology x Scale

Reading level is the organizing axis: it selects topology family, scale, fail-state
policy, and (with length) the backend. Story size and shape are a product decision
tied to the reader, never a side effect of which backend answered. Topology names
follow the standard gamebook vocabulary (Ashwell): Time Cave, Gauntlet,
Branch-and-Bottleneck, Loop-and-Grow.

| Band | Topology | Nodes | Endings | Decisions/path | State (tier) | Fail-state | Primary backend |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5-8 early | near-pure tree / Loop-and-Grow | ~42-46 short | 9-12 | ~3-6 | none (Tier 1) | **no death; try-again, comic** | Local Ollama / Modal Gemma 12B |
| 8-11 core | tree-dominant, light reconvergence | ~90-120 short (or ~45 at 250w) | ~20 | ~4-5 (max 7) | none (Tier 1) | failure/entrapment, adventure-forward | Modal Gemma 26B-A4B |
| 10-13 | Branch-and-Bottleneck (reconvergent leaves) | ~110-180 | ~19-28 | ~5-10 | light (item/flag) | horror variety, logical | Modal gpt-oss-120b |
| 13-16 | Gauntlet / Branch-and-Bottleneck (stateful) | 350-456 sections | 1 win + many fails | ~12-25 section hops | full (stats, inventory, dice) | resource-based, lethal | gpt-oss-120b / Opus authoring skill |

The graph-theory study (ages 9-12) validates the tree-dominant shape for 5-8 and
8-11 (two measured sources agree on node counts). It does **not** cover the
teen/stateful tier; Fighting Fantasy gamebooks are a deliberate teen-band product,
calibrated separately. The schema already enforces the state boundary: Tier 1
stories must declare no variables (`_check_tier_variables`); higher tiers carry
state. The 5-8 band is a new addition (current schema bands start at 8-11).

### Genre-faithful targets (from the reconciled four-source matrix)

- **Node word-size: ~150 words/node recommended** (the genre's flip-and-choose
  beat), versus the current 250-word assumption (1.7-2.5x the genre beat). Shorter
  nodes also yield more nodes, hence more room for reconvergent leaves and endings.
  Confirmable product choice; 250 stays valid as a modern-prose identity.
- **Endings via reconvergent leaves, not depth.** To raise ending count, add short
  leaves and bottlenecks, not deeper paths.
- **Depth budgets unchanged and correct** (~4-5 decisions average, ~7 longest).
  Path-length-in-nodes is a different metric from decisions-per-path; do not inflate
  depth from longest-path figures.
- **Choices per decision: 2-3** (mostly binary); rare 5-12-choice mystery hubs are
  premise-specific, not a default.
- **Reading level by age, independent of graph complexity.** Lexile anchors: core
  CYOA ~500-710L, Goosebumps ~480-490L, You Choose 590-720L, Dragonlarks
  ~480-570L. Move age up via premise, tone, and ending harshness before depth.
- **Edition-family anchoring:** tag any imported structural number with its edition
  (modern Chooseco vs vintage Bantam); they are not interchangeable.

## 4. Skeleton as a Data Artifact

A skeleton is a Storybook instance with structural content authored and prose slots
empty, plus fill metadata:

- **Graph:** nodes (ids, `is_ending`, ending type), choices (ids, target node),
  start node, declared `variables`, node `conditions`/`effects` (Tier 2+).
- **Fill metadata per node:** arc role (setup / rising / choice / climax /
  ending-type), and for Tier 2+ the **reachable state set** (computed statically
  from the graph) so prose is written consistent with every approach.
- **Classification:** `{topology_class, node_count, reading_band, ending_count,
  decision_count, state_depth, reconvergence_degree, fail_state_policy,
  edition_family}`. Drives library selection and model routing.

Skeletons are validated **once** at authoring time by the existing L1 gates
(references, choice targets, reachability via `_nodes_reaching_endings`,
termination, variable/condition/effect integrity). Stored as schema-valid Storybook
shells.

Creation: a small **hand-authored seed set** per cell first (proves the pipeline
against the real validator), then a **procedural skeleton generator** that emits
valid topologies (validated by the same gates) as the scaling step.

## 5. Generation Flow

```text
select skeleton (theme, reading_band, length; coverage-aware)
   -> bind theme (world/character bible, reading-level rules)  [stable, cached]
   -> fill nodes in batches against the fill contract          [parallel]
   -> assemble Storybook
   -> validate filled prose (content, reading level, fail-state, PII)
   -> prose-only repair loop if a content/reading gate fails
```

The orchestrator's Stage A (structure) is replaced by skeleton select+bind; Stage B
(prose) becomes batched fill; the repair loop shrinks to prose-only (reading level,
content policy, local coherence), never structural repair.

**Fill contract (transport-agnostic).** Each node fill is a self-contained task:
`{arc_role, incoming_context, reachable_state, choice_slots (target + label
intent), reading_level, fail_state_policy, content_policy}`. The same contract is
consumed by an automated provider or by the authoring skill, so fill logic is
independent of backend.

## 6. Backends: Two Modalities, One Contract

### 6.1 Runtime providers (automated, in the FastAPI app)

`GenerationProvider` adapters called by the worker. New `ModalProvider` is ~90% the
existing `OpenRouterProvider` (OpenAI-compatible HTTP, same `run_with_retries`
Layer-1 retry/backoff, same fence stripping), differing in base URL, auth, and a
cold-start-tolerant timeout. Streams SSE so the per-attempt timeout bounds
time-to-first-token (reusing the Ollama streaming lesson).

Modal endpoints are deployed out-of-band as config, not maintained Python:

```bash
modal endpoint create --name cyo-light    --model google/gemma-4-12b-it
modal endpoint create --name cyo-standard --model google/gemma-4-26B-A4B-it
modal endpoint create --name cyo-heavy    --model openai/gpt-oss-120b
```

Model picks are grounded in OpenRouter roleplay-category usage (creative narrative)
plus verified self-host VRAM: Gemma 4 26B-A4B is a 4B-active MoE on L40S;
gpt-oss-120b is 117B/5.1B-active MXFP4 fitting a single 80GB GPU (A100-80 or H100).
**Self-hosting decouples model choice from the ADR-003 allowlist**: the weights run
on our Modal GPU, so the model's creator never receives the prompt.

### 6.2 Authoring skill (Opus via Claude Code, offline, shareable)

The flagship path is **not** a runtime provider. It is a repo **skill/agent** that
runs inside Claude Code, using Claude subscription capacity (not API/OpenRouter).
It takes `skeleton + theme + fill contract`, fills the prose on Opus 4.8 (max
effort), validates against the schema, and emits a Storybook JSON imported like any
other story.

- **Concept-test enabler:** needs zero adapter code. Hand a hand-authored skeleton
  to the skill, fill on Opus, validate. Fastest test of "does skeleton-fill produce
  good stories?", and the right tool to crack the hardest teen/stateful skeletons
  first, then ratchet down to cheaper models.
- **Caching discipline:** keep the stable prefix (system prompt + skeleton +
  world/character bible + reading-level rules) constant and cached; vary only the
  per-node fill. Subscription + high cache hit rate fills a whole story far below
  per-token API cost.
- **Shareable:** packaged as a skill, any user with their own subscription can
  author stories.

### 6.3 Fallback and selection

- **Gemini 3 Flash via OpenRouter** is the allowlist-clean, creative-strong, cheap
  fallback when Modal credits are spent. A single floor is preferred over
  tier-matching open models on OpenRouter (which would reintroduce the data-policy
  question self-hosting avoids).
- **Monthly regime flip** (`generation_provider`) picks Modal-primary (credits) vs
  OpenRouter-primary (spent), not a per-request fallover. Manual; no credit-balance
  auto-detection (YAGNI).
- Per-tier cascade: `[Modal open model] -> [Gemini 3 Flash] -> [local Ollama, light
  tier only]`.

## 7. Model Alignment (Empirical)

Skeleton difficulty class -> model tier, *measured*, not guessed. v1 designs the
full difficulty range, runs every model against every class, and records a
skeleton-class -> cheapest-model-that-passes mapping.

| Skeleton class | Fill difficulty | Starting model hypothesis |
| --- | --- | --- |
| Tree / Loop-and-Grow (5-8, 8-11) | low | Gemma 4 12B / Ollama |
| Tree-dominant + light reconvergence (8-11) | medium | Gemma 4 26B-A4B |
| Branch-and-Bottleneck (10-13) | medium-high | gpt-oss-120b |
| Stateful Gauntlet / B&B (13-16) | high | gpt-oss-120b / Opus authoring skill |

## 8. Validator and Budget Changes

- **Add ending-count and decision-count floors** (quadruple-confirmed as the key
  gap; today `_BUDGETS` gates only `(min_nodes, max_nodes, max_branch_depth)` and
  `ending_count` is only checked for consistency). Prefer "more short leaves" over
  "deeper tree" when raising endings. Skeleton-authored stories pass by
  construction; the floor catches malformed skeletons and any non-skeleton path.
- **Add an age-gated fail-state gate** (new; child-safety, not style): hard
  no-death on the 5-8 band, failure/entrapment allowed at 8-11, horror variety at
  10-13, lethal/resource-based at 13-16. Enforced both as a validator gate
  (ending types) and a fill-contract constraint.
- **Compact budget profile** for the live-model path (the Ollama session):
  `band_budget(age_band, scale="standard"|"compact")`, threaded to both the prompt
  block and the gate so they cannot drift; scale driven by reading level, never by
  backend. Note the philosophy split: the compact profile is a stopgap for
  *model-built* graphs; the **skeleton path uses genre-faithful authored counts**
  (e.g. ~42-46 nodes at 5-8) and does not need the compact compromise.

| age_band | standard (min, max, depth) | compact (min, max, depth) |
| --- | --- | --- |
| 8-11 | (15, 30, 6) | (6, 12, 4) |
| 10-13 | (25, 50, 8) | (10, 18, 5) |
| 13-16 | (30, 60, 10) | (12, 24, 6) |

- Structural gates (references, orphans, reachability, termination) become
  invariants for skeleton-authored stories. State gates (variable/condition/effect)
  already exist and serve Tier 2+ gamebooks unchanged.

## 9. Cost Model

Automated Modal tiers (estimates; first deploy replaces with measured GPU-seconds).
Assumes ~20k output tokens for a standard story, +20% warm-idle; throughput Gemma 4
12B ~50, 26B-A4B ~90 (4B active), gpt-oss-120b ~100 tok/s (5.1B active).

| Tier / GPU | $/hr | ~$/standard story | per $10/mo |
| --- | --- | --- | --- |
| Gemma 4 12B / L4 | $0.80 | ~$0.10 | ~100 |
| Gemma 4 26B-A4B / L40S | $1.95 | ~$0.14 | ~70 |
| gpt-oss-120b / A100-80 | $2.50 | ~$0.24 | ~40 |

Full $30 unused triples the count. Local Ollama light-tier stories are $0. The Opus
authoring path is billed to the subscription.

**Exposure ratio (value metric).** A single playthrough exposes only ~15-20% of the
text; you pay to generate the full graph (~8-15k words) though one read sees
~2.5-3k. Higher reconvergence raises exposure and lowers the unseen-prose fraction,
so Branch-and-Bottleneck skeletons are more token-efficient per read than wide
trees. Factor exposure into per-story value, not just raw generation cost.

## 10. Security and Data Policy

- `modal_api_key` and endpoint tokens are secrets: never logged, validated by name
  on absence (mirrors OpenRouter key handling).
- Modal and Ollama are self-hosted inference; the prompt never reaches the model's
  creator. No real child PII reaches any model regardless (PII guard strips real
  names; only fictional briefs are sent).
- **ADR-003 update:** record the self-hosted exemption (creator receives no data),
  confirm Gemini 3 Flash on the OpenRouter allowlist; DeepSeek stays off-allowlist
  pending a separate decision.

## 11. Testing and Calibration

- **Concept test first (zero new app code):** author one skeleton per topology
  class, fill via the authoring skill on Opus, validate against the schema. Confirms
  skeleton-fill produces good stories and that the hardest classes are fillable.
- **Unit:** `ModalProvider` mirrors the OpenRouter adapter tests (transient->retry,
  leg-fatal mapping, fence strip, streaming accumulation) with an injected client;
  CI default stays `generation_provider=mock`.
- **Calibration:** deploy endpoints; record GPU-seconds and cold-start per endpoint;
  run every model against every skeleton class to build the alignment table;
  confirm each band clears its Lexile/FK gate; verify the 5-8 no-death gate; compare
  Modal-tier yield against Gemini 3 Flash on identical briefs.
- Coverage >= 80%; ruff, basedpyright strict, bandit, pip-audit green.

## 12. Phased Rollout

1. **Authoring skill + one hand-authored skeleton per class** -> concept test on
   Opus. (No app code; fastest validation of the core bet.)
2. **Skeleton schema/metadata + seed library** per (band, scale, topology) cell;
   validate with existing L1 gates; add coverage tracking.
3. **Validator floors** (endings, decisions) + **age-gated fail-state gate** +
   **compact budget profile** (the latter in flight on the Ollama session).
4. **`ModalProvider` + settings + `build_provider` branch**, behind
   `generation_provider=modal`, default unchanged.
5. **Deploy standard then heavy Modal endpoints**; calibrate; build the alignment
   table.
6. **Procedural skeleton generator** for scale.
7. **ADR-003 update**; add the 5-8 band; reading-level -> tier/skeleton routing.

## 13. Open Questions

- Node word-size: ~150 (genre-faithful, more leaves) vs 250 (modern prose). Leaning
  ~150; confirm.
- Per-tier reconvergence target (max indegree / state-variable count) before fill
  coherence degrades; resolve in calibration.
- Whether to add the 5-8 band to the schema/budgets in v1 or stage it after the
  8-11/10-13 tiers are proven.
- Whether the light tier defaults to local Ollama or Modal L4 once homelab
  TLS/throughput blockers clear.

## References

- Reconciliation (four sources): `docs/planning/research/cyoa-research-reconciliation.md`
- Graph-theory study: `docs/planning/research/commercial-cyoa-graph-theory-handoff.md`
  (Adams, Beckelhymer, Marr 2019, JHM 9(2), DOI 10.5642/jhummath.201902.05)
- Modal auto-endpoints: <https://modal.com/blog/introducing-auto-endpoints>
- gpt-oss-120b (117B/5.1B active, single 80GB GPU): <https://huggingface.co/openai/gpt-oss-120b>
- Gemma 4 family: <https://ai.google.dev/gemma/docs/core>
- Schema / validator: `src/cyo_adventure/storybook/models.py`,
  `src/cyo_adventure/validator/layer1.py`
- Provider protocol / factory: `src/cyo_adventure/generation/provider.py`
