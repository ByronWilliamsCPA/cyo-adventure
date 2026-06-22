---
title: "CYO Adventure - Project Vision & Scope"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Document the project vision, scope, and success criteria."
tags:
  - planning
  - scope
component: Strategy
source: "Project Ariadne scoping handoff (architecture rev 3, 2026-06-20)"
---

# Project Vision & Scope: CYO Adventure

> **Status**: Active | **Version**: 1.0 | **Updated**: 2026-06-20
> **Codename**: Ariadne (the thread that guides a reader through the maze of choices)

## TL;DR

CYO Adventure is a family app that plays branching "choose your path" gamebook
stories offline on a tablet or phone, paired with a content pipeline that turns a
short concept plus a drafting guide into a finished, safety-reviewed story. It is
built for one family's four children (roughly ages 9 to 15), and no story reaches a
child until a parent approves it.

## Problem Statement

### Pain Point

The goal is to recreate, for the children, the numbered-section gamebooks where each
decision sent the reader to a different section, so the story branched on the
reader's choices. Two problems sit underneath that:

- **Reading experience**: the branching needs a player that handles state-gated
  choices cleanly on mixed family devices, ideally offline.
- **Supply of stories**: hand-writing branching stories does not scale past what one
  person will produce, which is where an LLM comes in: feed it a concept and a
  drafting guide, and it writes a new branching story for the library.

### Target Users

- **Primary (readers)**: the four children, who span a wide range.
  - **Briella (9-10)**: gentle, shorter stories; benefits from read-aloud (8-11 band).
  - **Xander (12-13)** and **Bayden (14-15)**: longer branches with light
    state-tracking and more adventure (10-13 and 13-16 bands).
  - **Ariannah (17)**: top of the range, more likely to author or co-read than to be
    the target reader.
- **Primary (authors/approvers)**: the parents (Byron, and possibly Veronica),
  non-technical in operation. The approval flow must be a few clear screens, not a
  command line.
- **Context**: family-owned tablets, phones, and laptops at home; no app-store
  install friction is desired, which favors a PWA. Reading often happens offline.

That age spread, roughly 9 through 15, drives the reading-level and content controls
throughout the design.

### Success Metrics

- **Reader correctness**: 100% of published stories play to at least one ending with
  no dead ends or broken choices, verified by the validator before publish.
- **Generation yield**: at least 60% of generated stories pass the full validation
  gate with zero human edits to graph structure (prose tweaks allowed), measured over
  a 20-story sample.
- **Defect capture**: the validator rejects 100% of a curated "known-bad" corpus
  (dangling targets, orphan nodes, unreachable endings, unsatisfiable conditions,
  reading-level misses, unsafe content).
- **Safety**: 0 stories reach a child profile without a recorded parent approval,
  enforced by the state machine, not by convention.
- **Offline reliability**: a downloaded story plays start to finish with the network
  disabled.

## Solution Overview

### Core Value

Two systems that meet at a single file format: a **reader** plays stories and a
**content pipeline** produces them. Both treat a story as one artifact, a versioned
JSON graph of passages and choices with optional state (flags and small counters)
for the older kids. Pinning everything to that format keeps the two halves
independent: the LLM, the reader, or a future native app can each change without
disturbing the other side.

The pipeline is where the real engineering lives. Branching stories have a
structure-versus-prose tension, so generation runs in staged passes (structure, then
prose, then self-repair) with a deterministic validator between stages that proves
the graph holds together. Because the readers are children, a separate moderation
pass and a mandatory parent approval step gate every story before it appears in a
kid's library.

### Key Capabilities (MVP)

1. **Branching reader (PWA)**: tap a choice, jump to the next passage, with correct
   handling of state-gated choices. Works offline after a one-time download.
2. **Story format and runtime**: a versioned JSON schema plus a deterministic player
   that any client can run.
3. **Staged LLM generation**: a concept brief plus the drafting guide produces a
   finished story through structure, prose, and repair passes.
4. **Validation gate**: automated graph-integrity checks (no dead ends, no orphans,
   every choice points somewhere real), reading level, and length, run between
   generation stages and before publish.
5. **Safety and approval**: content moderation by age band plus a parent approval
   step that no story can skip.

Five capabilities, because that is what the MVP needs. Replay tracking, a story
editor, and read-aloud are valuable and scoped into later phases, not the core.

## Scope Definition

### In Scope (MVP)

- ✅ **Reader (PWA)**: offline play, save and resume, multiple endings per story.
- ✅ **JSON story format**: simple branching (Tier 1) and small state-tracking
  (Tier 2).
- ✅ **Concept intake + staged generation**: pluggable LLM provider behind a
  provider-agnostic interface.
- ✅ **Validation gate + content-moderation gate**: deterministic graph checks plus
  moderation by age band.
- ✅ **Parent approval workflow + per-child profiles**: age-band and reading-level
  limits enforced by the publish state machine.

### Out of Scope

- ❌ **Dice combat and skill/luck checks (Tier 3)**: randomness turns "every path
  reaches an ending" from a guarantee into a probability the deterministic gate
  cannot certify. Revisit only if the kids ask for it.
- ❌ **Any social, chat, or user-to-user feature**: a children's app has no reason
  to carry one.
- ❌ **Monetization, accounts for outside users, telemetry on minors.**
- 🔄 **Native iOS/Android apps**: deferred; the JSON format keeps this open.
- 🔄 **Full visual story editor (graph canvas)**: a lightweight node editor lands in
  Phase 4b; the rich canvas is later.
- 🔄 **Sharing beyond this family**: changes the privacy and account posture (see
  Assumptions and the "If shared beyond family" note in the tech spec).
- 🔄 **Per-passage illustrations or AI-generated images.**

## Constraints

### Technical

- **Platform**: Progressive Web App (React 19, TypeScript, Vite) reader plus a
  Python/FastAPI backend. See [ADR-002](./adr/adr-002-client-pwa.md).
- **Language**: Python 3.12 backend (uv, Ruff, BasedPyright), consistent with the
  migration off Poetry; pnpm for the frontend.
- **Deployment**: homelab-first behind Pangolin (zero-trust ingress) and Authentik
  (OIDC), with cloud-portable containers so Azure Container Apps is a drop-in
  alternative. See [ADR-004](./adr/adr-004-homelab-first-deployment.md).
- **Security baseline from day one**: detect-secrets, Semgrep managed rules, CodeQL,
  Trivy, CycloneDX SBOM, Cosign, centralized GitHub Actions.
- **Performance**: node transition under 50 ms (plays client-side from cache);
  validation under 2 s for a 200-node story; full offline play after one download.

### Business

- **Timeline**: roughly 11 to 16 weeks to the first usable release for a 1 to 2
  developer team (Phases 0-3 plus a minimal library-and-profiles slice). Full v1 with
  editor, engagement, and hardening is roughly 16 to 25 weeks. Ranges, not promises;
  the long pole is generation reliability, not the reader.
- **Resources**: a 1 to 2 developer team. Roles in the planning docs (PO, TL, BE, FE,
  INF) name accountability, not headcount.

### Decided release cut

Generation ships in the **first usable release**. The kids' first usable version
already writes its own LLM-generated stories, gated by validation and parent
approval. This elevates two items to Phase-0 hard blockers, because the first
external LLM call now ships in the first release: the provider data-handling decision
and the privacy controls (no real child PII in prompts; admin-only short-lived raw
outputs).

## Assumptions to Validate

- [ ] Children read on family-owned devices; a PWA (no app-store install) is the
      right delivery model, including iOS PWA storage-eviction quirks.
- [ ] A frontier LLM (Claude) holds branching structure well enough to clear the
      validation gate at the target 60% zero-structural-edit yield. See
      [ADR-003](./adr/adr-003-frontier-llm-generation.md).
- [ ] Tier-2 state can be kept small enough (a handful of variables) that the
      Layer-2 state-space validator stays under the configuration cap.
- [ ] The homelab can host Postgres, Redis, and MinIO behind Pangolin/Authentik with
      tested backups and restores.
- [ ] The provider's data-handling terms (standard API retention vs a
      zero-data-retention path) are confirmed directly with the provider at decision
      time, not assumed from the scoping documents.

## Related Documents

- [Architecture Decisions](./adr/README.md)
- [Technical Spec](./tech-spec.md)
- [Roadmap](./roadmap.md)
