---
title: "Blind-Spot Review Brief"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "How to run a frontier-model blind-spot review over new books, and how to consume its output without ticketing findings that are not real."
tags:
  - planning
  - quality
  - measurement
component: Development-Tools
---

# Blind-Spot Review Brief

> **Status**: Accepted | **Updated**: 2026-08-15
> **Serves**: [A11](./capability-register.md) (structural quality tools across the corpus)
> **Origin**: `AL-398`, scheduled as `UW-C265`

A blind-spot review asks a frontier model to read finished books and report only what the existing
coverage misses. It is the one instrument here that can find a defect class nobody has thought to
check for, and the 2026-08-14 run earned its place: two readers on different book sets, with no
contact, named the same five classes.

It is also the instrument most easily misread, which is what this document exists to prevent.

## The finding that shapes the whole procedure

**A reader's converged pattern is trustworthy. Its individual instances are not.** From the
2026-08-14 run, of four instances checked directly against the book JSON:

| Instance | Outcome |
| --- | --- |
| Reader B: `the-tide-pool-rescue` asserts counts with no declared state | verified, provable from metadata |
| Reader A: `the-night-market` endings presuppose an unwritten wish | **refuted**; all 15 paths pass through the node that establishes it |
| Reader A: snow-tunnel ending has no adult present | **overstated**; Mom watches from the porch |
| Reader A: hot-oven peeks are unsupervised | **overstated**; Grandma shuts the door in both nodes |

The classes those instances belonged to were all real. The asymmetry has a structural cause worth
naming rather than treating as a bad reader: a model reasons over the text in front of it and
cannot enumerate paths, so it is reliable about what a book **does** and unreliable about what
**every route through** the book does.

## Running one

1. **Give the reader the complete current coverage**, and say that only what falls outside it is
   in scope. As of 2026-08-15 that is: the 40 gate rules (L1, L2, PL, RL-13, CH, CG families), the
   7 judge criteria with full rubric text, the 6 deterministic prose measures, and W6's five
   declared-unobserved dimensions (`levels_of_meaning`, `text_structure`,
   `language_conventionality`, `knowledge_demands`, `information_state`). A reader not given the
   coverage will spend most of its output rediscovering it.
2. **Use at least two readers on overlapping book sets.** Overlap is what turns "a reader thought
   this" into a measurement. Give each five books, with two books in common.
3. **Require a node id and a verbatim quote for every instance**, so each one can be checked. An
   instance without them is not a finding, it is an impression.
4. Readers work read-only. They do not edit the corpus and do not write to the lessons log.

## Consuming one: the verification step is not optional

**No instance reaches a register row, a ticket, or a commit message until it has been checked
against the artifact.** Specifically:

- **Any claim about paths** ("this node presupposes X", "the reader may not have seen Y", "every
  ending assumes Z") is checked with `validator/paths.py`, never by re-reading the prose. This is
  the class the reader cannot see, and it is where the refuted flagship came from.
- **Any claim about what is absent** ("no adult is present", "nothing establishes this") is checked
  by reading the whole node and its neighbours. Both overstated instances above were absence claims
  that the surrounding sentence contradicted.
- **Any claim about metadata** (declared variables, topology, tier, counts) is checked against the
  JSON, and these are the cheapest and most reliable to confirm.

Report the checks with their outcomes, including the refutations. A review whose write-up contains
no refuted instances has probably not been checked.

## What to do with a class whose instances all fail

Keep the class and discard the instances. Convergence across independent readers is evidence about
the class; the instances are evidence about that reader's attention. `UW-C263` is the worked
example: the class was real, every checker built for it failed on measurement, and the finding
turned out to live in the skeleton catalogue rather than in any book.

## Related documents

- [Authoring lessons log](./authoring-lessons-log.md), `AL-396` through `AL-398` and `AL-402`
- [Unscheduled work register](./unscheduled-work-register.md), `UW-C263` through `UW-C265`
- `out/reviews/`, the 2026-08-14 reports and the verification write-ups
