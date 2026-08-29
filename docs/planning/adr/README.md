---
title: "Architecture Decision Records"
schema_type: planning
status: published
owner: core-maintainer
purpose: "Index and documentation for Architecture Decision Records."
tags:
  - planning
  - architecture
  - decisions
---

This directory contains Architecture Decision Records (ADRs) for CYO Adventure.

## What Are ADRs?

ADRs document significant architectural decisions along with their context and consequences. They help:

- Prevent architectural drift during AI-assisted development
- Provide rationale for technical choices
- Enable future developers to understand why decisions were made
- Maintain consistency across coding sessions

## ADR Index

| ADR | Title | Status | Date |
| --- | --- | --- | --- |
| [ADR-001](./adr-001-story-format-json-storybook.md) | Story format is a versioned JSON Storybook graph | Accepted | 2026-06-20 |
| [ADR-002](./adr-002-client-pwa.md) | Client is a Progressive Web App | Accepted | 2026-06-20 |
| [ADR-003](./adr-003-frontier-llm-generation.md) | Frontier LLM for generation, local model as fallback | Accepted | 2026-06-20 |
| [ADR-004](./adr-004-homelab-first-deployment.md) | Homelab-first deployment, Azure as the scale-out alternative | Accepted | 2026-06-20 |
| [ADR-005](./adr-005-mandatory-human-approval.md) | Mandatory human approval before any story reaches a child | Accepted | 2026-06-20 |
| [ADR-006](./adr-006-conditions-inhouse-evaluator.md) | Conditions use the JSONLogic shape with an in-house whitelisted evaluator | Accepted | 2026-06-20 |
| [ADR-007](./adr-007-raw-output-retention.md) | Raw LLM output retention policy for GenerationJob.report | Accepted | 2026-06-29 |
| [ADR-008](./adr-008-public-app-store-launch.md) | Public App Store launch with tiered subscription monetization | Proposed | 2026-07-02 |
| [ADR-009](./adr-009-supabase-platform.md) | Supabase as the managed platform for auth, database, and storage | Accepted | 2026-07-02 |
| [ADR-010](./adr-010-modal-review-and-gated-generation.md) | Modal for moderation review and an evidence-gated generation leg | Proposed | 2026-07-02 |
| [ADR-011](./adr-011-story-scale-framework.md) | Story-scale framework (reading band x length x style) | Accepted | 2026-07-02 |
| [ADR-012](./adr-012-supabase-cli-migrations.md) | Supabase CLI SQL migrations replace Alembic | Accepted | 2026-07-10 |
| [ADR-013](./adr-013-hybrid-pqc-readiness.md) | Hybrid post-quantum cryptography readiness | Accepted | 2026-07-11 |
| [ADR-014](./adr-014-device-authorized-kid-access.md) | Device-authorized kid access | Accepted | 2026-07-13 |
| [ADR-015](./adr-015-story-request-initiation-and-gating.md) | Universal story initiation with a guardian cost gate and an admin safety gate | Accepted | 2026-07-16 |
| [ADR-016](./adr-016-recommendation-sharing-social-boundary.md) | Recommendation sharing and the social boundary (three rings) | Accepted | 2026-07-16 |
| [ADR-017](./adr-017-ai-cover-art.md) | AI cover art per storybook version | Accepted | 2026-07-16 |
| [ADR-018](./adr-018-childrens-privacy-compliance.md) | Children's-privacy compliance architecture (COPPA, GDPR-K, AADC) | Proposed | 2026-07-16 |
| [ADR-019](./adr-019-parameterized-skeletons-theme-contracts.md) | Parameterized skeletons and machine-readable theme contracts | Accepted | 2026-07-19 |
| [ADR-020](./adr-020-mutation-derived-skeletons-and-catalog-growth.md) | Mutation-derived skeletons and catalog growth | Accepted | 2026-07-20 |
| [ADR-021](./adr-021-service-account-rls-and-worker-deployment.md) | Dedicated least-privilege service accounts, enforced RLS, and in-repo worker deployment | Accepted | 2026-07-20 |
| [ADR-022](./adr-022-tiered-rls-scoping.md) | Tiered RLS scoping (flat per-family enforcement on the high-sensitivity tables) | Proposed | 2026-07-24 |
| [ADR-023](./adr-023-story-personalization-slots.md) | Guardian opt-in story personalization (render-time slot substitution) | Accepted | 2026-07-29 |
| [ADR-024](./adr-024-bounded-backtracking-path-replay.md) | Bounded backtracking by forward path replay | Accepted | 2026-07-26 |
| [ADR-025](./adr-025-additive-storybook-schema-versioning.md) | Additive minor versioning for the Storybook schema | Accepted | 2026-08-01 |
| [ADR-026](./adr-026-rendered-stop-flow.md) | Rendered-stop flow of linear passages | Accepted | 2026-08-01 |
| [ADR-027](./adr-027-in-story-illustration.md) | In-story illustration (3-5 pilot) | Accepted | 2026-08-01 |
| [ADR-028](./adr-028-persistent-reader-characters.md) | Persistent reader characters | Accepted | 2026-08-06 |
| [ADR-029](./adr-029-web-accessibility-conformance.md) | Web accessibility conformance target and testing strategy | Accepted | 2026-08-11 |
| [ADR-030](./adr-030-engagement-correlation-privacy-review.md) | Children's-privacy review of the engagement-correlation analysis job | Proposed | 2026-08-28 |
| [ADR-031](./adr-031-first-party-friction-beacon.md) | Children's-privacy review of the first-party client friction beacon | Proposed | 2026-08-28 |

## Creating ADRs

### Automatic Generation

Run `/plan <project description>` to generate initial ADRs alongside other planning documents.

### Manual Creation

When making a new architectural decision:

```text
Create an ADR for [decision topic].
Use template: .claude/skills/project-planning/templates/adr-template.md
Save to: docs/planning/adr/adr-NNN-[decision-slug].md
```

## Naming Convention

ADRs follow this naming pattern:

```text
adr-NNN-short-description.md

Examples:
- adr-001-database-choice.md
- adr-002-auth-strategy.md
- adr-003-api-design.md
```

## When to Create an ADR

Create an ADR when:

- Choosing technology stack or framework
- Deciding on architectural patterns
- Selecting third-party services or libraries
- Making security or performance trade-offs
- Any decision that would be expensive to reverse

## ADR Lifecycle

```text
Proposed → Accepted → [Deprecated | Superseded]
```

- **Proposed**: Under discussion
- **Accepted**: Decision made and in use
- **Deprecated**: No longer relevant
- **Superseded**: Replaced by another ADR

## Follow-on work is part of the ADR (required for new and amended ADRs)

Every ADR that is `Proposed` or `Accepted` must state what work it creates, and every such item must
already have a home before the ADR merges. An ADR that decides something without scheduling its
consequences is how work goes missing: the 2026-07-28 sweep found 41 unscheduled items in this
directory alone, more than any other source.

Each ADR therefore carries a **Follow-on work** section listing every consequent item, and each item
must cite one of:

- a phase in [roadmap.md](../roadmap.md) or [PROJECT-PLAN.md](../PROJECT-PLAN.md),
- a `UW-*` row in the [unscheduled work register](../unscheduled-work-register.md), or
- a GitHub issue.

"Deferred", "future work", and "to be decided" are not homes. If the work genuinely cannot be
scheduled yet, add a `UW-*` row with status `blocked` and name the blocker; that is a real state and
the register is built to hold it. What is not acceptable is prose that directs work nowhere.

This rule is enforced going forward, on any ADR merged or materially amended from 2026-07-28
onward: PR review is the enforcement point, not automation. `scripts/check_work_linkage.py` does
not read `docs/planning/adr/`, so it cannot and does not check for a **Follow-on work** section;
what it does enforce is that a follow-on item, once it exists as a `UW-*` row, resolves to a real
disposition (see the [linkage contract](../unscheduled-work-register.md#the-linkage-contract)).
None of the 24 ADRs that predate this rule (including the two the 2026-07-28 sweep itself touched,
ADR-007 and ADR-021) carry a **Follow-on work** section yet; backfilling them is tracked as
`UW-A42` rather than implied by this paragraph.

## Template Reference

For the full ADR template, see the ADR template documentation in the Reference section, or refer to `.claude/skills/project-planning/templates/adr-template.md` in the project repository.

## More Information

- Document Guide: See `.claude/skills/project-planning/reference/document-guide.md` in the project repository
- Prompting Patterns: See `.claude/skills/project-planning/reference/prompting-patterns.md` in the project repository
