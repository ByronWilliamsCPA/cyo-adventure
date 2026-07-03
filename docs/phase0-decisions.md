---
title: "Phase 0 Decision Log"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Record the seven ratified Part V decisions that lock the architectural and scope choices before any app code is written."
component: Strategy
source: "docs/planning/PROJECT-PLAN.md section 5 Phase 0 (the seven ratified decisions); ADRs 001, 003, 004, 005"
tags:
  - planning
  - decisions
  - project
  - roadmap
---

## Overview

This page records the seven decisions ratified as "Part V" of the CYO Adventure scoping
handoff. These decisions are locked before any app code is written (Phase 0 exit gate).
Each entry states the decision, the one-line rationale, and the authoritative source.

> **Status note (2026-07-03):** This is a historical Phase 0 record. Three of these decisions
> have since evolved; the current position lives in later ADRs. The LLM provider is now
> OpenRouter-primary with an Ollama fallback (ADR-003 as amended, not Anthropic-direct). App
> authentication is now Supabase OIDC (ADR-009 supersedes Authentik as the app identity
> provider; Authentik remains only for homelab-internal ingress under ADR-004). The "first
> usable release" is the R1 internal-web rung of the R1/R2/R3 release ladder. The entries
> below are preserved as ratified; follow the linked ADRs for the current state.

Provider data-handling confirmation status is tracked as an OPEN BLOCKER; see
`docs/planning/privacy-model.md`.

---

## Decision 1: Custom JSON Storybook Format

**Decision**: Stories are authored and stored in a custom versioned JSON schema called the
"Storybook format," defined once in Pydantic v2 and exported to
`schema/storybook.schema.json`. Tier 1 covers simple branching (no state). Tier 2 adds a
small bounded-variable state layer.

**Rationale**: A purpose-built schema is the most reliable LLM generation target; static
safety properties (reachability, termination, no trap loops, state-space size) are
checkable by a deterministic validator; and the format is client-agnostic, so the reader,
the pipeline, and any future native app share one artifact without coupling.

**Source**: [ADR-001](planning/adr/adr-001-story-format-json-storybook.md)

---

## Decision 2: Frontier Provider (Claude) as Primary with Local Fallback

**Decision**: Anthropic Claude is the primary LLM for staged story generation, accessed
behind a `GenerationProvider` interface. Ollama (local Tesla P40) and OpenRouter are
fallback and development targets inside the same interface. A provider swap requires only
a configuration change.

**Rationale**: Frontier models hold branching structure and state-callback coherence far
better than smaller local models. Generation is infrequent, so per-call API cost is small
relative to the quality gain. The provider interface keeps switching cheap and retains the
local path for in-house iteration.

**Source**: [ADR-003](planning/adr/adr-003-frontier-llm-generation.md)

**Note**: The provider's data-handling terms (standard API retention vs a
zero-data-retention path) must be confirmed with the provider in writing before the first
real generation call in Phase 2. This is a Phase-0 hard blocker. See
`docs/planning/privacy-model.md` for the open blocker tracking entry.

---

## Decision 3: Homelab-First Hosting

**Decision**: The system deploys to the family homelab behind Pangolin (zero-trust ingress)
and Authentik (OIDC), using Docker containers managed by Dockge. Azure Container Apps is
a documented, tested drop-in alternative. Container images are pinned by tag; `latest` is
never used.

**Rationale**: Minors' data stays on hardware the family controls. The homelab already
runs Pangolin, Authentik, Postgres, Redis, and compatible storage; reusing it avoids a
new cost center. Cloud portability means the deployment is not locked to the homelab if
requirements change.

**Source**: [ADR-004](planning/adr/adr-004-homelab-first-deployment.md)

**Note**: The bare environment must be reachable through Pangolin as a Phase-0 exit
condition (plan item P0-10). See `docs/planning/privacy-model.md` for the associated open
blocker.

---

## Decision 4: Family-Only Reach

**Decision**: CYO Adventure is built for private use by one family. It serves four
children (Briella 9-10, Xander 12-13, Bayden 14-15, Ariannah 17) and their parents
(Byron and possibly Veronica). No accounts are created for outside users. No
user-to-user features are included.

**Rationale**: The privacy posture, data model, and moderation design are calibrated for
a known set of people on hardware the family controls. Expanding beyond the family
requires a new review: COPPA and state equivalents, age assurance, verifiable parental
consent, retention and deletion policy, vendor terms, incident response, and a published
privacy notice.

**Source**: [Project Vision: Scope Definition](planning/project-vision.md#scope-definition);
[Tech Spec: Privacy controls](planning/tech-spec.md#privacy-controls-family-only)

---

## Decision 5: Tier-2 Mechanics Cap (No Tier-3 Dice or Luck Checks in v1)

**Decision**: The story format supports Tier 1 (branching only) and Tier 2 (bounded
variables: booleans, small integers with `min`/`max`). Tier 3 (dice rolls, skill checks,
luck mechanics) is out of scope for v1.

**Rationale**: Randomness makes "every path reaches an ending" unprovable by the
deterministic validation gate. The Layer-2 state-space validator walks the configuration
closure and proves termination; that proof requires the state space to be finite and
enumerable. Dice and luck introduce probability that the validator cannot certify. Revisit
only if explicitly requested.

**Source**: [Project Plan: Section 2 Out of Scope](planning/PROJECT-PLAN.md#out-of-scope-v1);
[Tech Spec: Validation Gate Layer 2](planning/tech-spec.md#layer-2-state-space-tier-2-only)

---

## Decision 6: Lightweight Node Editor Deferred to Phase 4b

**Decision**: The first release ships without a story editing UI. A lightweight node
editor (read a story as a passage list, edit a single passage, re-roll a single branch to
trigger a repair pass, re-run validation) lands in Phase 4b after the first release. A
full visual graph canvas editor has no target phase.

**Rationale**: The reader, the generation pipeline, the validation gate, the moderation
pass, the approval workflow, and the library form the critical path to a first usable
release. An editing UI adds surface area and complexity that is not needed to prove the
system works. Deferring it reduces the risk that editor scope delays the first release.

**Source**: [Project Plan: Section 2 Out of Scope](planning/PROJECT-PLAN.md#out-of-scope-v1);
[Project Plan: Phase 4b](planning/PROJECT-PLAN.md#phase-4b-editor-engagement-and-ux-post-first-release)

---

## Decision 7: Generation Ships in the First Release

**Decision**: The LLM-powered staged generation pipeline (concept brief to validated,
moderated, guardian-approved story) ships as part of the first usable release, not as a
post-launch addition. Phases 0 through 3 plus the Phase 4a library-and-profiles slice
constitute the first usable release.

**Rationale**: The core value of the system is that a parent can generate a new story
for their child without writing it by hand. Deferring generation to a later release would
ship a reader with only hand-authored stories, which does not validate the core product
hypothesis. This decision elevates two items to Phase-0 hard blockers: the LLM provider
data-handling decision and the privacy controls (no real child PII in prompts; admin-only
short-lived raw outputs).

**Source**: [Project Plan: Section 1 Executive Summary](planning/PROJECT-PLAN.md#1-executive-summary);
[Project Plan: Phase 0 hard blockers](planning/PROJECT-PLAN.md#phase-0-foundations-1-2-weeks);
[ADR-003](planning/adr/adr-003-frontier-llm-generation.md);
[ADR-005](planning/adr/adr-005-mandatory-human-approval.md)
