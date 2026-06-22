---
title: "Privacy and Provider Data-Handling Model"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Document the data classification, retention rules, privacy controls, and open blockers for CYO Adventure's generation pipeline."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md sections Privacy controls, Data Protection, Security (2026-06-20)"
---

# Privacy and Provider Data-Handling Model

> **Status**: Draft | **Version**: 0.1 | **Updated**: 2026-06-20

## Overview

CYO Adventure is a family-only application serving four children. Because stories are
machine-generated and read by minors, the privacy controls and provider data-handling
decisions are Phase-0 hard blockers: they must be resolved before any real LLM call is
made in Phase 2.

This document covers data classification, what is and is not allowed in prompts, raw
output retention, moderation report persistence, deletion readiness, and prompt-injection
defense. Open blockers that gate the Phase 0 exit and the first Phase 2 LLM call are
listed at the end.

---

## Data Classification

Child-linked data is any record that can be associated with an identified or identifiable
child. The following are classified as child-linked:

- `child_profile` rows: `display_name`, `age_band`, `reading_level_cap`,
  `allowed_content_flags`, `tts_enabled`, `avatar`.
- `reading_state` rows: `current_node`, `var_state`, `path`, `save_slots`, keyed by
  `child_profile_id`.
- `completion` rows: `ending_id`, `found_at`, keyed by `child_profile_id`.
- Raw LLM generation outputs stored in object storage, if they were generated in a
  context where a concept brief containing profile attributes was used. These are
  admin-only.

The following are not child-linked on their own (they link to a family or a story, not
to an individual child):

- `storybook` and `storybook_version` records (family-linked, not child-linked).
- `concept` and `generation_job` records (family-linked).
- Moderation reports attached to `storybook_version` (persisted for audit; no child
  identifier unless a profile ID appears in the flagged text, which the privacy controls
  below prevent).

---

## No Real Child PII in Prompts

Concept briefs pass age band and a fictional reader profile to the LLM. They must not
contain:

- A real child's name (use fictional names or role descriptions such as "the protagonist").
- A real child's birthdate or age in a way that links to an identified individual.
- Sensitive traits, medical conditions, learning differences, or behavioral notes tied to
  a real child.
- Family member names or other identifying personal details.

The concept brief intake fields are: `title?`, `premise`, `protagonist` (name/age/role,
must be fictional), `point_of_view` (default 2nd person), `age_band`, `reading_level_target`,
`tier`, `tone`, `themes_allowed[]`, `content_nogo[]`, `target_node_count`, `ending_count`,
`structure_pattern`, `desired_variables[]?`, `special_constraints[]?`.

`age_band` is a categorical value ("8-11", "10-13", "13-16"); it identifies a generation
target, not an individual child. The backend must validate that the concept brief does not
contain free-text fields with real names before dispatching to the provider.

---

## Raw LLM Outputs and Prompt Text

Raw LLM outputs (the full text returned by the provider for each stage) and the prompt
text sent to the provider are admin-only and short-lived:

- **Prompt text**: store the prompt template version and a hash, not the full rendered
  prompt, where the rendered text could carry child-specific detail. The hash allows
  audit without persisting the content.
- **Raw generation outputs**: stored in object storage (`generation_job.raw_output_ref`)
  only as long as needed for debugging and repair pass analysis, then purged. The
  retention window is not yet defined; it must be set before Phase 2.
- **Access control**: `raw_output_ref` objects in MinIO are in a private bucket, not
  accessible via the story-serving path. Only admin-role users may retrieve them.

Moderation reports (the per-node flags and the moderation API response) persist with the
`storybook_version` record for audit. They contain node IDs and flag categories, not raw
child data.

---

## Deletion Readiness

A full deletion subsystem is a later deliverable. The requirement at Phase 0 is that the
data model does not make deletion impossible. The following rules apply:

- Child-linked data must be kept in known, enumerable places: `child_profile` rows in
  Postgres, `reading_state` rows in Postgres, `completion` rows in Postgres, raw
  generation outputs referenced by `generation_job.raw_output_ref` in MinIO.
- Child-linked data must not be scattered through structured logs, Sentry breadcrumbs, or
  application-level caches that are not enumerated in the data model.
- Sentry must not receive a child's reading content beyond a node ID or story ID. Exception
  events should carry correlation IDs, not reading-state snapshots.
- When a child profile is deleted, the owning service must be able to identify and purge
  all associated `reading_state` and `completion` rows. Cascades must be defined in the
  Alembic schema.

---

## Prompt-Injection Defense

Concept brief text is untrusted input. A malicious or malformed brief must not alter the
system prompt, bypass the safety constraints, or cause the model to produce content that
skips moderation.

Defense controls:

- The system prompt and safety constraints sent to the provider are fixed templates,
  rendered from versioned template files. Brief content is inserted only into designated
  user-turn slots and is never concatenated into the system prompt.
- The moderation pass runs independently of the generating model. Even if a brief causes
  the generator to produce unsafe content, the independent moderation pass and the
  mandatory guardian approval step remain in the path.
- Brief fields are validated against a strict schema before dispatch. Free-text fields
  (`premise`, `protagonist`, `special_constraints`) are length-limited and stripped of
  control characters before insertion.
- The generation orchestrator logs the prompt template version and the brief hash with
  every job. Any anomaly in moderation flags can be correlated back to the brief that
  triggered it.

---

## OPEN BLOCKERS

The following items gate both the Phase 0 exit and the first Phase 2 LLM call. No
generation call may be made with a real concept brief until both are resolved.

### Blocker 1: Anthropic API Data-Handling Terms

```python
# #CRITICAL: external resource: Anthropic API data-handling terms (standard retention
#            vs zero-data-retention) are unconfirmed.
# #VERIFY: confirm with the provider in writing before the first real generation call
#          in Phase 2; record the outcome here.
```

The standard Anthropic API retains inputs and outputs for a period defined in its terms
of service. A zero-data-retention (ZDR) agreement, where available, changes that posture.
Because concept briefs may contain age-band data and fictional content derived from a
child's interests, the applicable terms must be confirmed before dispatch.

**Required action**: contact Anthropic to determine whether the standard API retention
path or a ZDR path applies to this use case. Record the outcome (path chosen, contract
reference or API tier, effective date) in this section before Phase 2 begins. This is a
hard blocker for the Phase 0 exit gate (plan item P0-09).

**Status**: OPEN. Phase 2 cannot begin until this entry is completed and this file is
committed with the resolution.

---

### Blocker 2: Homelab Reachability Through Pangolin (P0-10)

```python
# #CRITICAL: external resource: homelab hosting reachability through Pangolin has not
#            been verified for this project's deployment.
# #VERIFY: confirm that a bare environment is reachable through Pangolin before the
#          Phase 0 exit gate; record the verification outcome in TECHNICAL_BASELINE.md
#          and cross-reference here.
```

The homelab must be reachable through the Pangolin zero-trust ingress before Phase 1
begins, so that integration tests and the CI environment can reach the deployed stack.
This is plan item P0-10 and a Phase 0 exit condition.

**Required action**: stand up the bare environment (Postgres, Redis, MinIO behind
Pangolin, Authentik configured with guardian and child roles). Verify reachability.
Record the outcome in `TECHNICAL_BASELINE.md` and update this entry with a cross-reference
date.

**Status**: OPEN. Phase 1 cannot begin until this entry is completed.

---

## If Shared Beyond Family

This design is calibrated for private family use. Before any non-family use, revisit with
legal counsel:

- COPPA (US) and state-level children's privacy equivalents.
- ICO Age Appropriate Design Code (UK) as a design reference.
- Age assurance and verifiable parental consent mechanisms.
- Retention and deletion policy suitable for a public service.
- Vendor terms covering the LLM provider, storage, and auth for a non-family audience.
- Incident response plan and a published privacy notice.

This note is a design reference, not legal advice.

---

## Related Documents

- [Tech Spec: Security](./tech-spec.md#security)
- [Tech Spec: Privacy controls](./tech-spec.md#privacy-controls-family-only)
- [Phase 0 Decision Log](../phase0-decisions.md)
- [ADR-003: Frontier LLM for generation](./adr/adr-003-frontier-llm-generation.md)
- [ADR-004: Homelab-first deployment](./adr/adr-004-homelab-first-deployment.md)
