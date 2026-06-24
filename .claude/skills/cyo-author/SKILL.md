---
name: cyo-author
description: Fill a CYO Adventure story skeleton with prose using the active model, then validate and import it. Use when authoring a story from a pre-authored skeleton (a structurally-valid Storybook shell whose node bodies hold <<FILL ...>> directives).
---

# CYO Author (skeleton fill)

## When to use

Invoke when given a skeleton file under `skeletons/<band>/<slug>.json` (or any
`<<FILL>>`-bearing Storybook shell) and asked to author the story.

## Procedure

1. **Load the skeleton.** Read the JSON. It is already a valid story graph; you only write
   prose. Never change `id`, `choices[].target`, `start_node`, node ids, `is_ending`,
   `ending`, `variables`, or `metadata`. Changing structure is a bug.

2. **Read the band rules.** From `metadata.age_band`, apply the per-band words/node target
   and fail-state policy (see `reference/skeleton-format.md`). Word targets: 3-5 ~75-100,
   5-8 ~100, 8-11 ~125-150, 10-13 ~175, 13-16 ~225, 16+ ~250 words per node.

3. **Fill each `<<FILL role=... words=... beats='...'>>` body** with prose that:

   - matches the band's word target and reading level (keep vocabulary/sentence length
     age-appropriate);
   - honors the `beats=` intent and the node's `role`;
   - sets up exactly the choices on that node (each `choice.label` is the action the prose
     should make available);
   - obeys the band fail-state policy (no death endings for 3-5 / 5-8).

   Replace the entire `<<FILL ...>>` string with the prose. Leave no `<<FILL` markers.

3b. **For Tier-2 (stateful) skeletons** (`metadata.tier` is 2): read the `variables`, each
   node's `on_enter` effects, and each choice's `effects`/`conditions`. The `beats=` directive
   names the relevant state; write prose consistent with the state reachable at that node (e.g.
   if `health` is low on the paths that reach a node, the diver feels the strain there). Never
   add, remove, or change a variable, effect, or condition; only write prose that fits the state
   the structure already defines.

4. **Keep the shared context stable for caching.** Fill nodes in one pass with the skeleton,
   band rules, and any world/character notes as a stable preamble; vary only the node being
   written. This maximizes prompt-cache reuse on the subscription.

5. **Write the filled story** to `out/<skeleton-slug>.filled.json`.

6. **Validate and import.** Run the import bridge:

   ```bash
   uv run python -m cyo_adventure.generation.import_cli out/<slug>.filled.json --family <family-uuid>
   ```

   If it reports a blocked gate, read the messages, fix the offending prose (never the
   structure), and re-run. If it reports an RL-13 reading-level warning, adjust vocabulary
   toward the band target; warnings do not block but should be addressed.

## Hard rules

- Structure is immutable; you only write prose.
- No `<<FILL` markers may remain.
- Respect the band fail-state policy (no death at 3-5 / 5-8).
