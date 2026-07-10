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
| [tech-spec.md](tech-spec.md) | Technical architecture and implementation details |
| [roadmap.md](roadmap.md) | Phased development roadmap and milestones |
| [adr/README.md](adr/README.md) | Architecture Decision Records index |
| [PROJECT-PLAN.md](PROJECT-PLAN.md) | Synthesized project plan: phase tasks, branch map, quality gates |
| [r1-deferred-debt-register.md](r1-deferred-debt-register.md) | Consciously-deferred debt inventory, including the R2 gate blockers |
| [naive-user-ux-testing-design.md](naive-user-ux-testing-design.md) | Naive-user UX test methodology (Playwright misuse regressions + Claude-for-Chrome comprehension prompts) |

See the [Project Setup Guide](../PROJECT_SETUP.md#project-planning-with-claude-code)
for instructions on generating these documents.
