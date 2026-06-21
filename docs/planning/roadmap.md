---
title: "CYO Adventure - Development Roadmap"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Document the phased implementation plan and milestones."
tags:
  - planning
  - roadmap
component: Strategy
source: "Project Ariadne scoping handoff (architecture rev 3, 2026-06-20)"
---

# Development Roadmap: CYO Adventure

> **Status**: Active | **Updated**: 2026-06-20
> **Codename**: Ariadne

## TL;DR

Build the schema first, then the player and reader, then the two-layer validator, then
generation, then safety and review, then library/profiles, editor, and hardening, across
six phases over roughly 16 to 25 weeks for a 1 to 2 developer team. The decided release
cut puts generation in the first usable release (Phases 0-3 plus a minimal
library-and-profiles slice, roughly 11 to 16 weeks).

## Timeline Overview

```text
Phase 0: Foundations    ████░░░░░░░░░░░░░░░░░░░░  (1-2 wks)  - Gate: lock decisions
Phase 1: Schema+Reader  ░░░░██████░░░░░░░░░░░░░░  (3-5 wks)  - Offline PWA, Layer-1 validator
Phase 2: Gen + Gate     ░░░░░░░░░░████████░░░░░░  (4-6 wks)  - Layer-2 validator, pipeline
Phase 3: Safety+Review  ░░░░░░░░░░░░░░██████░░░░  (3-4 wks)  - Moderation + approval (overlaps P2)
Phase 4a: Library       ░░░░░░░░░░░░░░░░░░████░░  (part of 3-5 wks) - FIRST RELEASE line
Phase 4b: Editor + UX   ░░░░░░░░░░░░░░░░░░░░████  (post-release) - Editor, TTS, tracker
Phase 5: Hardening      ░░░░░░░░░░░░░░░░░░░░░░██  (2-3 wks)  - Deploy, backups, restore drill
```

## Milestones

| Milestone | Target | Status | Dependencies |
|-----------|--------|--------|--------------|
| M0: Phase 0 exit gate (decisions locked, CI green) | Wk 1-2 | ⏸️ Planned | None |
| M1: Reader plays hand-authored stories offline | Wk 5-7 (internal demo) | ⏸️ Planned | M0 |
| M2: Concept-to-story pipeline passes the full gate | Wk 9-12 | ⏸️ Planned | M1 |
| M3: Parent approval gate enforced end to end | Wk 11-14 | ⏸️ Planned | M2 |
| M4: First usable release (generation + library) | Wk 11-16 | ⏸️ Planned | M3 |
| M5: Hardened, deployed, restore-tested v1 | Wk 16-25 | ⏸️ Planned | M4 |

---

## Phase 0: Implementation gate (1-2 weeks)

### Objective

Lock the decisions and artifacts that are expensive to change once code exists. No app
code until this gate passes. Tracked item-by-item in the Phase-0 punch list (PL-01
through PL-14).

### Deliverables

- [ ] MVP cut locked: a one-page in/out scope, approved (`docs/mvp-cut.md`).
- [ ] Decision log ratified: the seven Part V decisions (`docs/phase0-decisions.md`).
- [ ] Storybook schema v1 in Pydantic with JSON Schema export at
      `schema/storybook.schema.json`, plus at least 5 valid and 10 invalid fixtures.
- [ ] Story Runtime Semantics v1 documented and cross-signed by the player and validator
      owners.
- [ ] Validator design: rule ids and failure messages for Layer 1 and Layer 2, including
      the state-space approach and the configuration cap.
- [ ] Condition evaluator spec plus conformance fixtures for both in-house evaluators.
- [ ] Technical baseline (`TECHNICAL_BASELINE.md`): exact pinned versions; RQ and
      in-house evaluator confirmed; no `latest` image tags.
- [ ] Authorization matrix: endpoint access by guardian and child role, with IDOR
      negative tests listed.
- [ ] Privacy and provider data-handling model: data classification, retention,
      deletion-readiness.
- [ ] Repos scaffolded with the full CI and security baseline; hosting target chosen and a
      bare environment reachable through Pangolin.
- [ ] Drafting guide and stage prompt templates authored (migrate Appendix A from the
      scoping handoff). The 60% generation yield cannot be measured without them, and
      generation ships in the first release, so this is a Phase-0 precondition, not a
      Phase-2 afterthought.
- [ ] Configuration-cap worked example: document the practical Tier-2 variable budget
      that stays under the 100,000 ceiling (e.g. compute the reachable-config count for 2
      booleans plus one `int(0-5)` across ~50 nodes) so authors and the generator have a
      concrete budget, not just a ceiling.
- [ ] Alembic migration convention recorded in `TECHNICAL_BASELINE.md`: naming,
      down-revision policy, and a CI migration check.

### Success Criteria

- ✅ Schema, runtime semantics, validator rules, MVP scope, and the auth and privacy
  model are locked and cross-signed.
- ✅ A "hello world" Storybook validates against the v1 schema.
- ✅ CI runs lint, type check, and security scans green on the empty project.

### Tasks

| Task | Est. Hours | Status |
|------|------------|--------|
| Pydantic schema v1 + JSON Schema export + round-trip test | 8 | ⏸️ |
| Runtime Semantics v1 document | 6 | ⏸️ |
| Validator rule catalog (Layer 1 + Layer 2) | 8 | ⏸️ |
| Fixture corpus (5 valid, 10 invalid) | 8 | ⏸️ |
| Authz matrix + privacy model docs | 6 | ⏸️ |
| Repo scaffold + CI/security baseline green | 10 | ⏸️ |

### Dependencies

- Product Owner answers to the Open Decisions (resolved: see the PVS release cut).

---

## Phase 1: Schema, runtime, and reader MVP (3-5 weeks)

### Objective

Prove the format and the player with human-written stories before any LLM is involved.
This phase has no external network egress.

### Deliverables

- [ ] Deterministic player library (node traversal, state effects per Runtime Semantics
      v1, in-house condition evaluator).
- [ ] PWA reader: state-gated choices, offline caching (service worker + IndexedDB),
      save/resume, multi-device sync (revision-based, 409 reconciliation).
- [ ] Offline-conflict UX: the 409 "continue from this device" vs "use newer progress"
      dialog designed (copy plus a wireframe), and the iOS post-eviction "download
      needed" state, before the Playwright reconciliation test is written so the test
      asserts the real UX.
- [ ] Layer-1 graph validator with the valid/invalid fixture corpus from Phase 0.
- [ ] Two hand-authored stories: one Tier 1 (8-11 band) and one Tier 2 (older band).

### Success Criteria

- ✅ A child reads a downloaded story to multiple endings with the network disabled.
- ✅ State-gated choices appear and resolve correctly under different variable states.
- ✅ Progress survives reopening the app; a two-device conflict resolves without silent
  loss.
- ✅ The same fixtures play identically in the test harness and the browser.

### User Stories

#### US-101: Offline read to an ending

**As a** child reader
**I want** to play a downloaded story without a network connection
**So that** I can read anywhere, even offline.

**Acceptance Criteria**:

- [ ] A previously downloaded story plays start to ending with the network disabled.
- [ ] Reaching an ending records a completion that syncs on reconnect.

#### US-102: State-gated choice

**As a** middle-band reader
**I want** choices that depend on what I have collected to appear only when valid
**So that** the story reacts to my decisions.

**Acceptance Criteria**:

- [ ] A choice with a false condition is hidden, not shown-and-disabled.
- [ ] The player and validator agree on the condition's value (conformance fixtures pass).

### Dependencies

- Requires: Phase 0 schema and scaffold. Blocks: Phase 2.

---

## Phase 2: Validation gate and authoring pipeline (4-6 weeks)

### Objective

Generate stories that hold together, with the gate as the arbiter. First external LLM
call, so the privacy controls and provider data-handling decision are preconditions.

### Deliverables

- [ ] Layer-2 state-space validator (configuration walk, stateful dead-end, termination
      and loop escape, conditional usefulness, configuration cap).
- [ ] Generation orchestrator with staged passes (structure, prose, repair with the 3-cap
      and no-progress abort) and the provider interface (Claude primary; Ollama/OpenRouter
      fallback).
- [ ] Concept intake (no real child PII) and the RQ worker queue.
- [ ] The known-bad and Tier-2 state corpora and their tests.

### Success Criteria

- ✅ From a concept brief, the pipeline produces a story that passes the full gate with
  zero structural edits at least 60% of the time over a 20-story sample.
- ✅ The validator rejects 100% of the known-bad and Tier-2 corpora with correct rule and
  node attribution.
- ✅ No prompt sent to the provider contains a real child name, birthdate, or sensitive
  trait.

### Dependencies

- Requires: Phase 1 format, player, Layer-1 validator; Phase 0 provider and privacy
  decisions. Blocks: Phase 3, Phase 4a.

---

## Phase 3: Safety and review workflow (3-4 weeks; overlaps Phase 2)

### Objective

Make the kids-facing guarantee real.

### Deliverables

- [ ] Moderation pass (provider moderation plus an independent LLM-reviewer) scored
      against per-age-band policy.
- [ ] Publish state machine with the guardian-only approval transition.
- [ ] Parent review surface (read the story, see flagged passages, approve or send back).
- [ ] Provenance and audit on every published version.

### Success Criteria

- ✅ No story reaches a child profile without a recorded guardian approval (verified by
  attempting every transition path).
- ✅ Adversarial briefs are flagged and cannot be auto-published.

### Dependencies

- Requires: Phase 2 generation and validation.

---

## Phase 4: Library, profiles, editor, and engagement (3-5 weeks)

### Objective

Make authoring and reading pleasant. Split by the release cut: 4a ships in the first
release, 4b follows.

### Deliverables (4a, in the first release)

- [ ] Library browsing and per-child profiles with age-band and reading-level limits.
- [ ] The minimal guardian path to view, approve, publish, and assign a generated story to
      a profile.

### Deliverables (4b, after the first release)

- [ ] Lightweight node editor (read as a playthrough and a node list, edit a passage,
      re-roll a single branch, re-run validation).
- [ ] Ending tracker ("3 of 7 endings found"), bookmarks, and read-aloud (TTS).

### Success Criteria

- ✅ First release: a child sees only stories permitted for their profile; a guardian can
  assign an approved generated story to one or more children.
- ✅ 4b: concept to published through the UI alone including a small edit, and read-aloud
  works for the youngest band.

### Dependencies

- 4a requires Phases 2 and 3. 4b can follow the first release.

---

## Phase 5: Hardening and deploy (2-3 weeks)

### Objective

Production readiness on the homelab (or Azure).

### Deliverables

- [ ] Performance pass, offline-edge hardening, accessibility (WCAG AA basics: contrast,
      focus order, scalable text).
- [ ] Sentry wired on client and server; backups and a tested restore.
- [ ] Operator runbook and a short authoring guide for non-technical use.

### Success Criteria

- ✅ Deployed behind Pangolin with Authentik login; a restore from backup succeeds in a
  drill.
- ✅ Performance targets met on a real device on home wifi.

### Dependencies

- Requires: Phases 1-4.

---

## Critical Path

Schema (Phase 0) → player and reader plus Layer-1 validator (Phase 1) → Layer-2
state-space validator (Phase 2) → generation (Phase 2) → safety and review (Phase 3) →
library and editor (Phase 4). The schema is the keystone; settle and version it first.
Generation cannot precede the validator that judges it, and for Tier-2 that means the
Layer-2 validator gates generation, not just the graph checks. The honest long pole is
Phase 2, where generation reliability and the state-space validator absorb most of the
iteration; the reader itself is straightforward.

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Combinatorial branch explosion | M | H | Branch-and-bottleneck structure; node/depth budgets in the drafting guide and validator |
| Stateful runtime dead ends | M | H | Layer-2 state-space validator; configuration cap bounds the walk |
| LLM coherence across branches | H | M | Structure-first staged generation; validator; repair loop (3-cap, no-progress abort); small Tier-2 state |
| Unsafe or off-band content | L | H | Independent moderation + mandatory guardian approval + age-band policy; never auto-publish |
| Generation cost and latency | M | L | Infrequent generation; async worker; immutable cached outputs; per-family quota |
| Condition-evaluator divergence | L | H | Tiny in-house interpreter; property-tested for totality; shared conformance fixtures |
| Multi-device progress loss | M | M | Revision-based concurrency; explicit conflict resolution; server canonical |
| Scope creep (dice, combat, sharing) | M | M | Explicitly out of v1; revisit only on demand |
| iOS PWA storage eviction | M | M | IndexedDB as cache only; Postgres canonical; sync on every choice |

## Definition of Done

A feature is complete when:

- [ ] Code reviewed and approved.
- [ ] Tests written and passing (≥ 80% line, 70% branch; 90% on critical paths).
- [ ] Documentation updated.
- [ ] No linting or type errors (Ruff, BasedPyright).
- [ ] Security scans show no high/critical findings.
- [ ] Merged to main via a signed commit.

The roadmap is complete when every phase meets its acceptance criteria, a generated story
can travel from concept to a child's tablet with a parent's approval and play offline to
multiple endings, and the validator (Layer 1 and Layer 2) provably rejects the known-bad
and Tier-2 corpora.

## Related Documents

- [Project Vision](./project-vision.md)
- [Technical Spec](./tech-spec.md)
- [Architecture Decisions](./adr/)
