---
title: "Stage A: Structure Generation Prompt Template"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Reusable prompt template for Stage A (Structure) of the staged generation pipeline."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md section Authoring Pipeline, Stage A; docs/planning/drafting-guide.md"
---

# Stage A: Structure Generation Prompt Template

> **Status**: Draft | **Version**: 0.1 | **Updated**: 2026-06-20

## Usage

This template is rendered by the generation orchestrator and passed to the `GenerationProvider`
as the user-turn message for Stage A. The system prompt is a fixed, versioned template (not
shown here) that sets the role, safety constraints, and output format requirements. This
template provides the task-specific content.

Placeholders in `{curly_braces}` are substituted by the orchestrator before dispatch:

- `{concept_brief}`: the structured concept brief (JSON), validated before insertion.
- `{schema_rules}`: the Layer-1 and Layer-2 validator rule catalog (rule IDs and
  descriptions), so the model knows exactly what the skeleton must satisfy.
- `{drafting_guide}`: the full text of `docs/planning/drafting-guide.md`, providing node
  budgets, structure patterns, variable rules, and common failure modes.

Do not concatenate brief content into the system prompt. Insert it only into the designated
slot in this user-turn template.

---

## Template

```
You are generating the skeleton (Stage A: Structure) of a branching story for a
choose-your-own-adventure reading app used by children.

## Concept Brief

{concept_brief}

## Schema and Validator Rules

The skeleton you produce must satisfy all Layer-1 graph rules. The rules are listed
below. Read them before generating; do not produce a skeleton that violates them.

{schema_rules}

## Drafting Guide

Follow the drafting guide for node budgets, structure patterns, and variable rules.

{drafting_guide}

## Your Task

Produce a story skeleton as valid JSON conforming to the Storybook schema. The skeleton
must contain:

1. The top-level metadata fields: `schema_version`, `id` (use a UUID v4), `version`
   (set to 1), `title` (propose one if not in the brief), and the `metadata` block
   (`age_band`, `reading_level`, `tier`, `themes`, `estimated_minutes`,
   `ending_count`, `content_flags`).

2. A `variables` array (empty for Tier 1; for Tier 2, declare each variable with
   `name`, `type`, `initial`, `min` and `max` for integers, and `description`).

3. A `start_node` field naming the first node id.

4. A `nodes` array. For Stage A, each node must have:
   - `id`: a stable slug (e.g. `n_cellar_entrance`), unique within the story.
   - `body`: a one-line beat description, not prose (e.g. "The protagonist enters the
     cellar and sees two doors."). Full prose is written in Stage B.
   - `on_enter`: an array of effects (may be empty). For Stage A, list the effects
     as structured objects even if the values are placeholders; the validator will
     check them.
   - `choices`: an array of choices for non-ending nodes. Each choice must have:
     - `id`: a unique slug (e.g. `c_left_door`).
     - `label`: a one-line action description (not final prose; Stage B writes it).
     - `target`: the node id the choice leads to (must be a node id in this skeleton).
     - `condition`: omit if unconditional; include the JSONLogic object if conditional.
     - `effects`: an array (may be empty).
   - `is_ending`: `false` for non-ending nodes; `true` for ending nodes.
   - `ending`: include on ending nodes only, with `id` (stable slug), `type`
     (`success`, `failure`, `bittersweet`, or `open`), and `title`.
   - `tags`: an array (may be empty).

5. At least `ending_count` ending nodes (from the concept brief), each with a
   distinct `ending.id`.

## Constraints

- Every node id referenced in a `choice.target` must be a node id that exists in the
  `nodes` array of this skeleton. Do not generate forward references.
- Every node must be reachable from `start_node` by following choice targets.
- Every non-ending node must have at least one choice.
- No orphan nodes (nodes unreachable from `start_node`).
- The `id` field on the Storybook is a UUID v4 string.
- Node ids and choice ids are snake_case slugs prefixed with `n_` and `c_`
  respectively (e.g. `n_forest_path`, `c_go_left`).
- For Tier-2 stories: conditions use only the permitted operators (`var`, `==`, `!=`,
  `<`, `<=`, `>`, `>=`, `and`, `or`, `!`). Every variable referenced in a condition
  must be declared in the `variables` array. Do not use arithmetic, string operators,
  or `if`/ternary.
- Stay within the node count and depth budgets from the drafting guide for the
  requested `age_band` and `tier`.

## Output

Respond with valid JSON only. Do not include prose before or after the JSON. Do not
include markdown fences. The validator will parse your response as JSON; any non-JSON
content will cause the job to fail.
```

---

## Post-Generation Step

After receiving the Stage A response, the generation orchestrator:

1. Parses the JSON and validates it against the Layer-1 graph rules (schema, reference
   integrity, reachability, termination, no trap loops, condition consistency, length
   budget) and, for Tier-2 stories, a partial Layer-2 check covering variable
   declarations and condition operator whitelist.
2. If validation passes, the skeleton is saved as the approved structure and the job
   advances to Stage B (Prose).
3. If validation fails, the job routes to Stage C (Repair) with the validator report.
   If the skeleton fails repair after 3 attempts, the job is routed to human review;
   it is never auto-published.

---

## Related Documents

- [Tech Spec: Authoring Pipeline](../tech-spec.md#authoring-pipeline-staged-generation)
- [Stage B Prose Prompt](./prose.md)
- [Stage C Repair Prompt](./repair.md)
- [Drafting Guide](../drafting-guide.md)
