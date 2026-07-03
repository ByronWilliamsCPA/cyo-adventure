---
title: "MVP Cut"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Define the in-scope and out-of-scope boundaries for the first release of CYO Adventure."
component: Strategy
source: "docs/planning/PROJECT-PLAN.md section 2 Scope; docs/planning/project-vision.md section Scope Definition"
tags:
  - planning
  - scope
  - boundaries
  - mvp
---

## Overview

This page records the agreed scope boundary for R1, the internal-web release of CYO Adventure
(Phases 0 through 3 plus the Phase 4a library-and-profiles slice). It is a one-page
reference that the team checks before adding anything to a phase branch.

Approved: OPEN: owner approval required

---

## In Scope (First Release)

The following capabilities are committed for the first release:

1. **Reader (PWA)**: offline play, save and resume, multi-device sync, multiple endings.
   The reader works on family-owned tablets, phones, and laptops without an app-store
   install. ([ADR-002](planning/adr/adr-002-client-pwa.md))

2. **JSON Storybook format**: Tier 1 (simple branching, no state) and Tier 2 (small
   state-tracking with booleans and bounded integers). The schema is versioned and
   exported to `schema/storybook.schema.json`. ([ADR-001](planning/adr/adr-001-story-format-json-storybook.md))

3. **Staged LLM generation**: concept brief to finished story through Structure (Stage A),
   Prose (Stage B), and Repair (Stage C) passes behind a `GenerationProvider` interface.
   OpenRouter is the primary provider; Ollama is the local development and fallback target.
   ([ADR-003](planning/adr/adr-003-frontier-llm-generation.md))

4. **Validation gate**: deterministic Layer-1 graph checks (schema, reference integrity,
   reachability, termination, no trap loops, condition consistency, length budget) plus
   Layer-2 state-space analysis for Tier-2 stories (stateful dead-ends, stateful
   termination, conditional usefulness, configuration cap of 100,000 reachable
   configurations).

5. **Content-moderation gate**: provider moderation API plus an independent LLM-reviewer
   pass, scored per age band. Any hit flags the nodes and forces human review; safety hits
   never auto-publish.

6. **Parent approval workflow**: publish state machine enforcing a mandatory guardian
   approval before any story is visible to a child.
   ([ADR-005](planning/adr/adr-005-mandatory-human-approval.md))

7. **Per-child profiles**: `child_profile` records with `age_band`, `reading_level_cap`,
   `allowed_content_flags`, and `tts_enabled`; enforced by the library API, never trusted
   from the client.

8. **Homelab deployment**: behind Pangolin (zero-trust ingress) and Authentik (OIDC), with
   cloud-portable containers. Azure Container Apps is a documented drop-in alternative.
   ([ADR-004](planning/adr/adr-004-homelab-first-deployment.md))

---

## Out of Scope (v1)

The following are explicitly excluded from the first release. They are not deferred
by accident; each has a documented reason.

1. **Dice combat and skill/luck checks (Tier 3)**: randomness makes "every path reaches
   an ending" unprovable by the deterministic validation gate. The gate cannot certify
   a probability. Revisit only if explicitly requested.

2. **Social, chat, or user-to-user features**: a children's app has no reason to carry
   them. Excluded permanently unless the scope and privacy posture are revisited.

3. **Monetization, accounts for outside users, or telemetry on minors**: out of scope
   for this family-only deployment.

4. **Native iOS/Android apps**: the JSON Storybook format keeps this option open for
   the future; the PWA covers the MVP need without app-store friction.

5. **Rich visual graph canvas editor**: a lightweight node editor (read passages as a
   list, edit a passage, re-roll a branch) lands in Phase 4b after the first release.
   The full canvas editor is later still.

6. **Sharing beyond this family**: requires a revisited privacy posture covering COPPA
   and state equivalents, age assurance, verifiable parental consent, retention and
   deletion policy, vendor terms, incident response, and a published privacy notice.

7. **Per-passage illustrations or AI-generated images**: deferred; no target phase
   assigned.

8. **Ending tracker, bookmarks, and read-aloud (TTS)**: these engagement features land
   in Phase 4b after the first release, along with the node editor.

---

## Change Control

Any addition to the in-scope list requires an update to this file with the rationale and
the source planning document that authorizes it. Do not add scope that is not present in
`docs/planning/project-vision.md`, `docs/planning/tech-spec.md`, or the ADRs.
