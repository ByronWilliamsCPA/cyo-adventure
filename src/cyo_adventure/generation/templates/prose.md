You are writing the prose (Stage B: Prose) for a branching story for a
choose-your-own-adventure reading app used by children. The story structure has already
been validated; your task is to write the final prose without changing the structure.

The approved story skeleton is in the user message that follows these instructions.
Read the drafting guide and the validator rules first; then replace every `body` and
every choice `label` in that skeleton with final prose, changing nothing else.

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
   match the ending's `valence` (`positive`, `neutral`, `negative`) and `kind`.
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

<!-- @user -->

## Approved Story Skeleton

The following JSON skeleton passed the validator. It contains one-line beat descriptions
in each `body` field and action descriptions in each choice `label`. Replace every `body`
with full passage prose. Replace every choice `label` with the final choice text shown
to the reader. Change nothing else.

{approved_skeleton}
