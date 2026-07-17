---
title: "Validation Rule Catalog"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Define stable rule IDs, failure messages, and pass/fail semantics for every validation gate check."
tags:
  - planning
  - specifications
  - validation
component: Development-Tools
source: "tech-spec.md section 'Validation gate (deterministic, no LLM)'"
---

# Validation Rule Catalog

> **Status**: Accepted | **Version**: 1.2 | **Updated**: 2026-07-16
> **Scope**: All stories (Layer 1, Policy); Tier-2 stories only (Layer 2); all stories
> advisory (RL); all stories always-human (SAFE)

---

## Purpose

Every rule the validator applies gets a stable ID, a description, and a failure-message
template here. Rule IDs are the stable references used in validation reports, repair-stage
prompts, and the known-bad corpus. Adding, removing, or renumbering a rule requires a revision
to this document.

---

## Pass/Fail vs Advisory Semantics

| Category | Behaviour | Blocks publish? |
|----------|-----------|-----------------|
| Layer 1 (L1) | Pass/fail | Yes |
| Policy (PL) | Pass/fail (PL-19 story-mean sub-check is advisory) | Yes |
| Layer 2 (L2) | Pass/fail | Yes (Tier-2 only) |
| Reading Level (RL) | Advisory | No (warns only) |
| Safety (SAFE) | Always human-routed | Yes (routes to human review, not auto-rejected) |

Layer 1, Policy, and Layer 2 are hard gates, run in that order (`validator/gate.py::run_gate`):
any failure fails the generation job (it lands in `failed`, not `passed`), so the story never
advances to `in_review`. The Policy layer's PL-19 story-mean words-per-node sub-check is the
one advisory exception; its per-node word-cap sub-check is still blocking. The reading-level
check warns and logs but does not block. A safety hit routes the generation job to
`needs_review` for mandatory human review; the validator does not auto-reject, but no
auto-publish path exists when the flag is set.

**Layer 2 applies to Tier-2 stories only.** Running Layer 2 on a Tier-1 story (which carries
no variables and has deterministic visibility for all choices) is a no-op and must not produce
false failures.

---

## Layer 1: Graph Rules (All Stories)

Layer 1 runs first, on every story. Layer 2 does not run if Layer 1 fails, because the graph
must be sound before a state-space walk is meaningful.

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| L1-1 | 1 | **Schema conformance**: the Storybook JSON must validate against `schema/storybook.schema.json`. | `L1-1 schema: document does not conform to Storybook schema v{schema_version}: {validation_errors}` |
| L1-2 | 1 | **Reference integrity**: `start_node` must exist in `nodes`; every `choice.target` must be an existing node id; all node ids must be unique; all choice ids must be unique within the story; every `ending.id` must be unique within the story. | `L1-2 ref: {ref_type} '{target}' not found or not unique in story '{story_id}' (referenced from {source})` |
| L1-3 | 1 | **Reachability**: BFS from `start_node` must reach every node. Nodes unreachable from `start_node` are errors, not warnings. | `L1-3 reach: node '{node_id}' is unreachable from start_node '{start_node}' in story '{story_id}'` |
| L1-4 | 1 | **Termination (graph)**: every non-ending node must have at least one choice; every node must have at least one path to an ending node; every ending node must have zero choices and a complete `ending` block. | `L1-4 term: node '{node_id}' {reason} in story '{story_id}' (no path to any ending / missing ending block / non-ending node has zero choices)` |
| L1-5 | 1 | **No trap loops (graph)**: every strongly connected component must have at least one exit edge leading toward an ending. A SCC with no exit is a trap loop. | `L1-5 trap: strongly connected component containing node '{node_id}' has no exit edge in story '{story_id}' (nodes in SCC: {scc_nodes})` |
| L1-6 | 1 | **Condition and effect consistency**: conditions must use only whitelisted operators; every variable referenced in a condition or effect must be declared in `variables`; comparisons must agree in type with the declared variable type; no reachable transition may push an `int` variable past its declared `min` or `max`. | `L1-6 logic: {issue_type} in story '{story_id}' at {location}: {detail} (var='{var}', declared_type={declared_type}, bound={bound}, attempted={attempted})` |
| L1-7 | 1 | **Length budget**: node count must be within the (band x length x style) cell budget single-sourced in `validator/band_profile.py` (band-based per [ADR-011](./adr/adr-011-story-scale-framework.md), not tier-based); branch depth must be within bounds; `metadata.ending_count` must equal the count of distinct ending nodes found in `nodes`. | `L1-7 budget: {budget_type} out of range in story '{story_id}': {actual} (allowed {min}..{max})` |

---

## Layer 2: State-Space Rules (Tier-2 Stories Only)

Layer 2 performs a configuration walk. A **configuration** is `(node_id, var_state)`. The walk
starts at `(start_node, initial_var_state)`, computes visible choices using the canonical
condition evaluator, applies effects per the Runtime Semantics transition order, and explores
the closure of reachable configurations. The default configuration cap is 100,000 (see L2-12).

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| L2-8 | 2 | **Configuration walk**: the walk starts at `(start_node, initial_var_state)` and explores every configuration reachable via valid transitions using the canonical evaluator and transition order. If the walk cannot be completed (malformed condition returns non-boolean), the story fails. | `L2-8 walk: configuration walk failed at node '{node_id}' with var_state {var_state}: {reason}` |
| L2-9 | 2 | **Stateful dead-end**: any reachable non-ending configuration with zero visible choices is a dead end. A reader in this state cannot proceed. | `L2-9 dead: node '{node_id}' with var_state {var_state} is a stateful dead end (no visible choices, not an ending) in story '{story_id}'` |
| L2-10 | 2 | **Stateful termination and loop escape**: every reachable configuration must have at least one path to an ending configuration. Every reachable cycle must have at least one configuration in the cycle with a visible choice leading out of the cycle toward an ending. | `L2-10 escape: configuration ('{node_id}', {var_state}) has no path to any ending in story '{story_id}' (cycle with no escape / dead configuration chain)` |
| L2-11 | 2 | **Conditional usefulness**: a conditional choice (one with a non-trivial `condition`) that is invisible in every reachable configuration is flagged as a dead branch. This is a warning elevated to a failure: a condition that is never satisfiable is either a generator bug or a story logic error. | `L2-11 dead-branch: choice '{choice_id}' on node '{node_id}' is never visible in any reachable configuration in story '{story_id}' (condition always false)` |
| L2-12 | 2 | **Configuration cap**: if the reachable configuration set exceeds the ceiling (default 100,000), the walk aborts immediately and the story fails. This prevents unbounded validator runtime on pathological stories. | `L2-12 cap: reachable configuration set exceeded the ceiling of {cap} configurations in story '{story_id}' (state space too large; reduce variable count or tighten bounds)` |

---

## Reading Level (Advisory, All Stories)

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| RL-13 | Advisory | **Reading level**: Flesch-Kincaid grade (computed by textstat) for each node `body` is compared to `metadata.reading_level.target +/- tolerance`. Any node outside the tolerance range generates a warning. This check warns and logs; it never hard-fails, because FK scores are noisy at passage length and the parent makes the final call. | `RL-13 level: node '{node_id}' FK grade {actual:.1f} outside target {target} +/- {tolerance} in story '{story_id}' (advisory only)` |

---

## Safety (Always Human-Routed, All Stories)

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| SAFE-14 | Safety | **Safety moderation**: moderation runs over all `body` and `label` text against the age-band policy. Any hit flags the specific nodes and forces mandatory human review. A safety flag does not auto-reject the story; it routes the generation job to `needs_review` (not `passed`), so the story cannot reach `published` until a global admin clears or escalates the flag. No auto-publish path exists when a SAFE-14 flag is set. | `SAFE-14 safety: node '{node_id}' flagged by moderation for age band '{age_band}' in story '{story_id}': {flag_detail} (requires human review)` |

---

## Policy Gate (Age-Band, All Stories)

Runs after Layer 1 passes and the Storybook parses, on the typed model plus the choice
graph (`validator/policy.py`). Most findings are ERROR-severity and blocking; PL-19 is
advisory (WARNING). PL-15..PL-18 are defined below; PL-19 (words-per-node), PL-20
(fastest-finish arc floor), and PL-21 (off-matrix rejection) are specified in
[ADR-011](./adr/adr-011-story-scale-framework.md) rather than duplicated here. PL-22
(band profile not configured, fail closed) is a runtime invariant rather than an
age-safety rule in its own right; it is defined below.

| Rule ID | Layer | Description | Failure Message Template |
|---------|-------|-------------|--------------------------|
| PL-15 | Policy | **Ending-kind policy**: no ending whose `kind` is in the band's `forbidden_ending_kinds` (the no-death / no-capture rule). | `PL-15 policy: ending kind '{kind}' is forbidden for band '{age_band}' in story '{story_id}'` |
| PL-16 | Policy | **Content ceiling**: each `metadata.content_flags` value must not exceed the band's `content_ceiling` for that flag (ordered-enum comparison). | `PL-16 policy: {flag} '{level}' exceeds band '{age_band}' ceiling '{ceiling}' in story '{story_id}'` |
| PL-17 | Policy | **Floors**: distinct endings must meet `min_endings`; decision nodes (non-ending nodes with >= 2 choices) must meet `min_decisions`, both possibly scaled and counted from the graph. | `PL-17 floor: {n} ending(s)/decision node(s) below {scope} minimum {min} in story '{story_id}'` |
| PL-18 | Policy | **Topology verify**: declared `metadata.topology` must be admissible for the class inferred from graph metrics (networkx classifier). | `PL-18 topology: declared '{topology}' is not admissible for the graph (admissible: {admissible}) in story '{story_id}'` |
| PL-22 | Policy | **Band profile fail-closed**: added 2026-07-16 per the owner ruling (fail closed). When a story's age band has no configured `BandProfile` (`validator/band_profile.py::profile_for` returns `None`), the gate emits this single blocking finding and returns immediately instead of silently skipping PL-15/16/17 for that band. Unreachable through any valid, enum-constrained `age_band` today (a lockstep test pins the `AgeBand` enum against the configured profiles), so this is a runtime backstop, not a normal-path rule. See `validator/policy.py::validate_policy` and `tests/unit/test_policy.py::test_validate_policy_fails_closed_when_profile_is_none`. | `PL-22 policy: band profile not configured for band '{age_band}' in story '{story_id}'; refusing to validate age safety` |

---

## Rule Application Order

The validator applies rules in this order:

1. L1-1 through L1-7 (graph; all stories). Stop if any L1 rule fails.
2. PL-15 through PL-21, plus the PL-22 fail-closed guard (age-policy gate; all stories).
   PL-19 is advisory; the rest block. PL-22 fires only when the band has no configured
   profile, in which case it is the sole finding and PL-15..PL-21 do not run.
3. L2-8 through L2-12 (state-space; Tier-2 only). Stop if any L2 rule fails.
4. RL-13 (advisory; all stories). Log warnings; continue.
5. SAFE-14 (moderation; all stories). Flag nodes; block auto-publish if flagged.

Stopping at the first Layer-1 failure is allowed for efficiency; all Layer-1 failures may also
be collected in a single pass before reporting, which is preferred for repair-stage prompts
(Stage C needs all failing node ids, not just the first).

---

## Failure Report Format

Each failure in a validation report carries:

```json
{
  "rule_id": "L1-6",
  "severity": "error",
  "story_id": "...",
  "node_id": "n_cave",
  "choice_id": "c_lantern_door",
  "message": "L1-6 logic: condition in story 'dungeon-escape' at choice 'c_lantern_door': operator 'if' is not whitelisted (var='courage', declared_type=int)"
}
```

The repair-stage prompt (Stage C) receives the array of failure objects and instructs the model
to address only the flagged node ids and rule violations, changing nothing else.

---

## Related Documents

- [Tech Spec: Validation Gate](./tech-spec.md#validation-gate-deterministic-no-llm)
- [Story Runtime Semantics v1](./runtime-semantics.md)
- [Condition Evaluator Specification](./condition-evaluator-spec.md)
- [Configuration Cap Worked Example](./configuration-cap.md)
- [ADR-006: In-house condition evaluator](./adr/adr-006-conditions-inhouse-evaluator.md)
