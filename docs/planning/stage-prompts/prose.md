---
title: "Stage B: Prose Generation Prompt Template"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Reusable prompt template for Stage B (Prose) of the staged generation pipeline."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md section Authoring Pipeline, Stage B; docs/planning/drafting-guide.md"
---

# Stage B: Prose Generation Prompt Template

> **Status**: Draft | **Version**: 0.1 | **Updated**: 2026-06-20

## Usage

This template is rendered by the generation orchestrator and passed to the `GenerationProvider`
as the user-turn message for Stage B. The system prompt is a fixed, versioned template (not
shown here). Stage B receives the approved skeleton from Stage A as its primary input.

Placeholders in `{curly_braces}` are substituted by the orchestrator before dispatch:

- `{approved_skeleton}`: the full Storybook JSON skeleton that passed Stage A validation.
  The node `body` fields contain one-line beats; choice `label` fields contain action
  descriptions. Stage B replaces these with final prose.
- `{drafting_guide}`: the full text of `docs/planning/drafting-guide.md`, providing voice,
  reading level, word-count guidance, and Tier-2 rules.
- `{schema_rules}`: the validator rule catalog, so the model knows which properties it
  must not alter.

Do not send the Stage A prompt or the concept brief again in Stage B. The approved
skeleton is the contract; Stage B is prose only.

---

## Template

```
You are writing the prose (Stage B: Prose) for a branching story for a
choose-your-own-adventure reading app used by children. The story structure has already
been validated; your task is to write the final prose without changing the structure.

## Approved Story Skeleton

The following JSON skeleton passed the validator. It contains one-line beat descriptions
in each `body` field and action descriptions in each choice `label`. Replace every `body`
with full passage prose. Replace every choice `label` with the final choice text shown
to the reader. Change nothing else.

{approved_skeleton}

## Drafting Guide

Follow the drafting guide for voice, reading level, word-count targets, and Tier-2
variable rules.

{drafting_guide}

## Validator Rules (Do Not Violate)

The following rules will be re-checked after Stage B. Do not change anything that would
cause these rules to fail.

{schema_rules}

## Your Task

Produce the complete Storybook JSON with all `body` fields and choice `label` fields
written as final prose. The output must be the full Storybook JSON, not a diff or patch.

### Prose requirements

1. **Voice**: second person, present tense throughout. Address the reader as "you."
2. **Reading level**: match the `reading_level.target` in the skeleton metadata.
   Refer to the drafting guide for FK grade targets and sentence-length guidance by
   age band.
3. **Node body length**: 80-150 words for the 8-11 band; 100-200 words for the 10-13
   band; 120-250 words for the 13-16 band. Stay within these ranges.
4. **Choice labels**: imperative or action description; 5-12 words; must match the
   semantic intent of the beat description in the skeleton.
5. **Ending nodes**: the `body` of an ending node should bring the story to a
   satisfying close. Do not end with a question or a choice. The emotional tone should
   match the `ending.type` (`success`, `failure`, `bittersweet`, `open`).
6. **Age-appropriate content**: follow `metadata.themes` and the system-level content
   policy. Do not introduce content categories not listed in `themes_allowed` from the
   original brief.

### What you must not change

- `id` on the Storybook, on any node, on any choice, or on any ending block.
- `target` on any choice.
- `condition` on any choice.
- `effects` on any choice or `on_enter` on any node.
- `is_ending` on any node.
- `variables` declarations.
- `start_node`.
- `metadata` fields (including `age_band`, `tier`, `reading_level`, `ending_count`).

Changing any of these fields will cause the Stage B validation to fail and route the
job to Stage C (Repair).

## Output

Respond with valid JSON only. Do not include prose before or after the JSON. Do not
include markdown fences. The validator will parse your response as JSON; any non-JSON
content will cause the job to fail.
```

---

## Post-Generation Step

After receiving the Stage B response, the generation orchestrator:

1. Parses the JSON and validates it against the full validator: Layer-1 graph rules,
   Layer-2 state-space rules (for Tier-2 stories), and the reading-level advisory check.
2. If validation passes, the story advances to the moderation pass and then to guardian
   review. It is never auto-published.
3. If validation fails (structural regression introduced during prose writing), the job
   routes to Stage C (Repair) with the validator report. If repair is exhausted after 3
   attempts, the job is routed to human review.

---

## Related Documents

- [Tech Spec: Authoring Pipeline](../tech-spec.md#authoring-pipeline-staged-generation)
- [Stage A Structure Prompt](./structure.md)
- [Stage C Repair Prompt](./repair.md)
- [Drafting Guide](../drafting-guide.md)
