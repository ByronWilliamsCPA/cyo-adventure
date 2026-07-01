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
|-----|-------|--------|------|
| [ADR-001](./adr-001-story-format-json-storybook.md) | Story format is a versioned JSON Storybook graph | Proposed | 2026-06-20 |
| [ADR-002](./adr-002-client-pwa.md) | Client is a Progressive Web App | Proposed | 2026-06-20 |
| [ADR-003](./adr-003-frontier-llm-generation.md) | Frontier LLM for generation, local model as fallback | Proposed | 2026-06-20 |
| [ADR-004](./adr-004-homelab-first-deployment.md) | Homelab-first deployment, Azure as the scale-out alternative | Proposed | 2026-06-20 |
| [ADR-005](./adr-005-mandatory-human-approval.md) | Mandatory human approval before any story reaches a child | Proposed | 2026-06-20 |
| [ADR-006](./adr-006-conditions-inhouse-evaluator.md) | Conditions use the JSONLogic shape with an in-house whitelisted evaluator | Proposed | 2026-06-20 |
| [ADR-007](./adr-007-raw-output-retention.md) | Raw generation output is retained briefly, then purged | Proposed | 2026-06-24 |
| [ADR-008](./adr-008-first-release-trust-boundary.md) | The first release verifies identity at the API, not at the ingress | Proposed | 2026-07-01 |

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

## Template Reference

For the full ADR template, see the ADR template documentation in the Reference section, or refer to `.claude/skills/project-planning/templates/adr-template.md` in the project repository.

## More Information

- Document Guide: See `.claude/skills/project-planning/reference/document-guide.md` in the project repository
- Prompting Patterns: See `.claude/skills/project-planning/reference/prompting-patterns.md` in the project repository
