You are correcting the prose of a filled story skeleton (Stage 1: Fidelity Repair)
for a choose-your-own-adventure reading app used by children. You already filled a
pre-authored skeleton, but your fill did not stay faithful to the skeleton's original
FILL directives: one or more nodes missed their target word count, left an unfilled
directive in place, or changed structure that must be preserved exactly.

The story to correct and the list of fidelity violations are in the user message that
follows these instructions.

## Your Task

Produce the complete, corrected Storybook JSON. Fix ONLY the fidelity violations listed
in the user message. Unlike a validator repair, a fidelity fix usually means rewriting
the prose body of the affected node so it lands near the target length and depicts the
same beat, so you SHOULD rewrite the body of any node named in a violation.

### Rules for fidelity repair

1. **Fix each listed violation directly.**
   - A word-count violation means rewrite that node's `body` so its length lands near
     the stated target, while depicting the exact same events and outcome (the beat).
   - An unfilled FILL directive means write the final prose the directive asks for
     (role, word count, and beat), adapted to the story's theme.
   - A structural violation means restore the original structure: a changed id, target,
     condition, effect, is_ending, variables, start_node, or metadata field must be put
     back exactly as the skeleton had it. Changing structure is itself a fidelity
     violation.

2. **Preserve everything not named in a violation.** Do not rewrite the body or choice
   labels of nodes that are not flagged, and do not change any structural field
   (ids, targets, conditions, effects, is_ending, variables, start_node, metadata).

3. **Do not introduce new violations.** The fidelity checks re-run on your output; a fix
   that repairs one node's word count but breaks another node's is still a failure.

## Output

Respond with valid JSON only. Do not include prose before or after the JSON. Do not
include markdown fences. The output must be the full Storybook JSON, not a diff or patch.

<!-- @user -->

## Story to Correct

The following JSON is the filled story that did not pass the Stage 1 fidelity checks.

{filled_story}

## Fidelity Violations

The following fidelity problems were found. Fix each one, and change nothing else:

{fidelity_violations}
