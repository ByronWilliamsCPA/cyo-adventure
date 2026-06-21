---
title: "Stage C: Repair Prompt Template"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Reusable prompt template for Stage C (Repair) of the staged generation pipeline, with no-progress abort and cap-at-3 rules."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md section Authoring Pipeline, Stage C; docs/planning/PROJECT-PLAN.md Phase 2 deliverables"
---

# Stage C: Repair Prompt Template

> **Status**: Draft | **Version**: 0.1 | **Updated**: 2026-06-20

## Usage

This template is rendered by the generation orchestrator and passed to the `GenerationProvider`
as the user-turn message for each Stage C repair attempt. The system prompt is a fixed,
versioned template (not shown here).

Placeholders in `{curly_braces}` are substituted by the orchestrator before dispatch:

- `{approved_skeleton}`: the full Storybook JSON from the most recent stage (Stage A
  output if the structural skeleton failed; Stage B output if prose regression caused
  validation failure). This is the artifact being repaired.
- `{validator_report}`: the structured report from the validator, listing exactly which
  rules failed, which node ids are implicated, and the specific rule violation messages.
- `{failing_node_ids}`: a comma-separated list of node ids that appear in the validator
  report, extracted by the orchestrator for clarity.

Stage C is invoked after Stage A or Stage B if the validator finds failures. It may also
be invoked after a prior Stage C attempt if the repair did not clear all failures.

---

## Orchestrator Rules (Enforced Before Dispatch)

The orchestrator applies the following rules before rendering and dispatching this prompt.
These are not suggestions; they are implemented in code.

1. **Cap at 3 attempts**: Stage C may be called at most 3 times per generation job
   (across all stage failures combined). On the 3rd exhaustion, the job is not
   dispatched again; it is routed to human review. The attempt counter is persisted in
   `generation_job.status` and is never reset within a job.

2. **No-progress abort**: before dispatching attempt N, the orchestrator computes a
   hash of the validator report from attempt N-1 and a hash of the full Storybook JSON
   from attempt N-1. If both hashes are unchanged from the prior attempt (the model
   produced the same output and the validator produced the same report), the repair is
   aborted immediately without dispatching. The job is routed to human review.

3. **Never auto-publish**: a job that exits Stage C (whether by exhaustion, no-progress
   abort, or an unexpected error) is never transitioned to `in_review` automatically.
   It is moved to `needs_revision` and requires a guardian to re-trigger generation or
   escalate to human review.

4. **Route to full regeneration or human review on exhaustion**: the orchestrator
   surfaces both options in the `generation_job` status: re-trigger a full regeneration
   (starting from Stage A) or escalate to human review. The guardian chooses; the system
   does not choose automatically.

---

## Template

```
You are repairing a branching story (Stage C: Repair) for a choose-your-own-adventure
reading app used by children. The story was generated in a previous stage but did not
pass the validator. Your task is to fix only the failing nodes listed below and correct
only the specific rule violations reported. Change nothing else.

## Story to Repair

The following JSON is the story that failed validation. It may be a structure skeleton
(from Stage A) or a fully proofed story (from Stage B).

{approved_skeleton}

## Validator Report

The following report lists every rule that failed, the node ids implicated, and the
specific violation message for each failure. Read the report carefully before making
any changes.

{validator_report}

## Failing Node IDs

The following node ids appear in the validator report. Restrict your changes to these
nodes only:

{failing_node_ids}

## Your Task

Produce the complete, corrected Storybook JSON. Apply the minimum change that resolves
each violation in the validator report.

### Rules for repair

1. **Name only the failing node ids**: address only the nodes listed in
   `{failing_node_ids}`. Do not rewrite, restructure, or improve nodes that are not
   in that list.

2. **Fix the specific rule violations**: the validator report describes each violation
   with a rule id and a message. Address each one directly. Do not speculate about
   other potential issues.

3. **Change nothing else**: do not alter node ids, choice ids, ending ids, `target`
   fields, `condition` fields on choices that are not in `{failing_node_ids}`, or
   `variables` declarations unless the validator report explicitly flags them as the
   source of a failure.

4. **Do not introduce new violations**: a repair that fixes one rule failure and
   introduces another is still a failed validation. The validator will re-run on your
   output.

5. **Preserve all prose outside the failing nodes**: do not rewrite `body` or choice
   `label` fields on nodes not in `{failing_node_ids}`, even if you believe the prose
   could be improved.

### Common repair patterns

- **Orphan node** (rule: reachability): add a `target` on an existing choice in a
  reachable node pointing to the orphan node. Do not delete the orphan.
- **Dead end** (rule: stateful dead-end or graph termination): add a choice to the
  dead-end node that leads toward an existing ending. The choice label must make
  narrative sense in context.
- **Dangling target** (rule: reference integrity): correct the `target` value to an
  existing node id. Do not create a new node; use an existing one that fits the
  narrative context.
- **Bound overflow** (rule: condition consistency): reduce the `inc` value, widen the
  `max`, or add a condition that prevents the increment from being taken when the
  variable is at its bound.
- **Dead branch** (rule: conditional usefulness): either remove the condition (making
  the choice unconditional) or adjust a prior effect so the condition can be satisfied
  by some reachable state.

## Constraints

- The repaired story must be valid JSON conforming to the Storybook schema.
- Node ids, choice ids, and ending ids must not be renamed.
- Do not add new nodes unless the validator report explicitly states that a missing
  node is the source of a failure (this is rare; dangling targets are more commonly
  fixed by correcting the `target` value).
- For Tier-2 stories: conditions must use only permitted operators (`var`, `==`, `!=`,
  `<`, `<=`, `>`, `>=`, `and`, `or`, `!`). Do not introduce arithmetic or string
  operators.

## Output

Respond with valid JSON only. Do not include prose before or after the JSON. Do not
include markdown fences. The validator will parse your response as JSON; any non-JSON
content will cause the repair attempt to fail and count against the cap.

If you cannot resolve a violation without restructuring the story in a way that would
change nodes outside the failing set, state that explicitly in a JSON comment field
`"_repair_note"` at the top level of the Storybook object. The orchestrator will read
this field and route the job to human review.
```

---

## Post-Repair Step

After receiving the Stage C response, the generation orchestrator:

1. Checks for a `_repair_note` field at the Storybook root. If present, the job is
   routed immediately to human review without running the validator.
2. Parses the JSON and runs the full validator (Layer 1 and, for Tier-2, Layer 2).
3. If validation passes, removes the `_repair_note` field (if any was added by a
   prior attempt), advances the story to moderation, and then to guardian review.
   The story is never auto-published.
4. If validation fails, increments the attempt counter. If the counter is below 3 and
   the no-progress check does not abort, dispatches another Stage C attempt.
5. If the counter reaches 3 or the no-progress check fires, moves the job to
   `needs_revision` and surfaces the regeneration or human-review options to the
   guardian. Never auto-publishes, never auto-transitions to `in_review`.

---

## Related Documents

- [Tech Spec: Authoring Pipeline](../tech-spec.md#authoring-pipeline-staged-generation)
- [Stage A Structure Prompt](./structure.md)
- [Stage B Prose Prompt](./prose.md)
- [Drafting Guide](../drafting-guide.md)
- [ADR-005: Mandatory human approval](../adr/adr-005-mandatory-human-approval.md)
