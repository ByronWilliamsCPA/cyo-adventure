---
title: "CYO Adventure - Planning"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Index and navigation for project planning documents."
tags: [planning, index]
component: Strategy
source: "/plan command generation"
---

> **Status**: Navigation index (does not require regeneration)

---

## Planning Documents

This directory contains the planning documents for `CYO Adventure`. The four
`/plan`-generated documents (vision, tech spec, roadmap, ADRs) define the blueprint;
[PROJECT-PLAN.md](PROJECT-PLAN.md) is the synthesized plan that sequences them into phases,
and [r1-deferred-debt-register.md](r1-deferred-debt-register.md) tracks remaining debt. Scope reaches users
on a three-rung release ladder: R1 internal (web PWA, feature-complete 2026-07-03), R2
limited (iOS via TestFlight), and R3 public launch (App Store).

| Document | Purpose |
|----------|---------|
| [project-vision.md](project-vision.md) | Project vision, scope, and success metrics |
| [capability-register.md](capability-register.md) | Persona capability contract (K/G/A/S IDs): scope checkoff sheet and testing basis |
| [tech-spec.md](tech-spec.md) | Technical architecture and implementation details |
| [roadmap.md](roadmap.md) | Phased development roadmap and milestones |
| [adr/README.md](adr/README.md) | Architecture Decision Records index |
| [PROJECT-PLAN.md](PROJECT-PLAN.md) | Synthesized project plan: phase tasks, branch map, quality gates |
| [r1-deferred-debt-register.md](r1-deferred-debt-register.md) | Consciously-deferred debt inventory, including the R2 gate blockers |
| [unscheduled-work-register.md](unscheduled-work-register.md) | Directed-but-unscheduled work (UW-* IDs) found by the 2026-07-28 sweep, each with a proposed phase |
| [story-structure-diversity-critical-analysis.md](story-structure-diversity-critical-analysis.md) | Root-cause analysis of the structural ceiling limiting story diversity: seven compounding causes |
| [story-structure-improvement-plan.md](story-structure-improvement-plan.md) | Execution plan for the critical analysis: 5 stages, 24 deliverables (SQ-01..SQ-24), 7 owner gates |
| [story-structure-implementation-briefs.md](story-structure-implementation-briefs.md) | Per-deliverable briefs for SQ-01..SQ-24: file/function anchors, change spec, test plan |
| [research/README.md](research/README.md) | Index and provenance for the research base behind ADR-011 and the story structure/diversity work |
| [naive-user-ux-testing-design.md](naive-user-ux-testing-design.md) | Naive-user UX test methodology (Playwright misuse regressions + Claude-for-Chrome comprehension prompts) |

See the [Project Setup Guide](../PROJECT_SETUP.md#project-planning-with-claude-code)
for instructions on generating these documents.
