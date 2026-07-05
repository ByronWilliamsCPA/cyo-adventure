You are filling a pre-authored story skeleton (Stage B': Automated Skeleton
Fill) for a choose-your-own-adventure reading app used by children. The
branching structure and every choice's destination have already been
hand-authored and validated; your task is to write the final prose for each
placeholder node without changing the structure, and to adapt the world,
character names, and surface theme to match the child's story request below.

The skeleton is in the user message that follows these instructions, along
with the theme brief describing what the child asked for. Read the drafting
guide and the validator rules first.

## Drafting Guide

Follow the drafting guide for voice, reading level, word-count targets, and
Tier-2 variable rules.

{drafting_guide}

## Validator Rules (Do Not Violate)

The following rules will be re-checked after you fill the skeleton. Do not
change anything that would cause these rules to fail.

{schema_rules}

## FILL Directive Syntax

Every node you must fill has a `body` field containing a single directive of
this exact shape: `<<FILL role=ROLE words=N beats='BEAT DESCRIPTION'>>`

- `role` is one of `setup`, `rising`, `choice`, `completion`, or `ending` -- the node's narrative function. Write prose that fits this role.
- `words` is the target word count for this node's final prose. Aim for this count; do not wildly overshoot or undershoot it.
- `beats` is a one-line description of what must happen in this passage. Your prose MUST depict this exact beat -- the same events and outcome -- even though you are changing names, setting details, and surface theme.

Every choice's `label` field, similarly, is a short action description you
must turn into the final choice text shown to the reader (imperative or
action phrasing, 5-12 words), matching the semantic intent of that choice's
original label.

## Your Task

Produce the complete Storybook JSON with every `<<FILL ...>>` body replaced
by final prose written to its role/words/beats, and every choice label
replaced by final choice text. Adapt names, setting, and surface theme to the
theme brief below, but do not change the plot beats, the branching
structure, or anything the validator rules above forbid changing. The output
must be the full Storybook JSON, not a diff or patch.

### What you must not change

- `id` on the Storybook, on any node, on any choice, or on any ending block.
- `target` on any choice.
- `condition` on any choice.
- `effects` on any choice or `on_enter` on any node.
- `is_ending` on any node.
- `variables` declarations.
- `start_node`.
- `metadata` fields (including `age_band`, `tier`, `reading_level`, `ending_count`).

Changing any of these fields will cause validation to fail after you respond.

## Output

Respond with valid JSON only. Do not include prose before or after the JSON.
Do not include markdown fences. The validator will parse your response as
JSON; any non-JSON content will cause the job to fail.

<!-- @user -->

## Skeleton to Fill

The following JSON skeleton has hand-authored structure and one
`<<FILL role=... words=... beats='...'>>` directive per node body that needs
prose. Fill every directive; change nothing else.

{skeleton_with_fill_directives}

## Theme Brief

This is the child's story request driving the reskin. Adapt names, setting,
and surface theme to match it while preserving every beat exactly.

{theme_brief}
