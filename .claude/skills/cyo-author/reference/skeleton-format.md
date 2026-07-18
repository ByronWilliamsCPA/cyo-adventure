# CYO Adventure Skeleton Format Reference

Reference for the `<<FILL>>` directive grammar, per-band prose targets, and ending type
conventions used by the `cyo-author` skill.

---

## The `<<FILL>>` directive

A skeleton node's `body` field holds a single `<<FILL>>` directive in place of prose.
The grammar is:

```
<<FILL role=ROLE words=N beats='SHORT INTENT'>>
```

### Attributes

| Attribute | Required | Description |
|-----------|----------|-------------|
| `role` | Yes | The node's narrative role in the story graph. One of: `setup`, `rising`, `choice`, `climax`, or an ending subtype such as `completion` or `failure`. |
| `words` | Yes | Approximate target word count for this node's prose. Match the band's words/node target (see table below). |
| `beats` | Yes | A short single-quoted phrase describing the narrative event that must occur in this node. The author fulfills the beat while setting up the choices listed on the node. |

### Authoring rule

Replace the entire `<<FILL ...>>` string (including the angle brackets) with finished prose.
No `<<FILL` markers may remain in the output JSON.

---

## Per-band prose targets

| Band | Words/node | Reading level (Lexile anchor) | Topology family | Fail-state policy |
|------|-----------|-------------------------------|-----------------|-------------------|
| 3-5 | ~75-100 | ~480-570L | Linear / Loop-and-Grow | NO death endings; outcomes must be comic or always-recover |
| 5-8 | ~100 | ~480-570L | Near-pure tree / Loop-and-Grow | NO death endings; try-again or comic outcomes only |
| 8-11 | ~125-150 | ~500-710L | Tree-dominant, light reconvergence | Failure and entrapment allowed; keep tone adventure-forward |
| 10-13 | ~175 | ~490-720L | Branch-and-bottleneck (reconvergent leaves) | Horror variety and logical failure allowed |
| 13-16 | ~225 | Middle-grade+ | Gauntlet / branch-and-bottleneck (stateful) | Resource-based failure; lethal endings allowed |
| 16+ | ~250 | Advanced | Deep Gauntlet / branch-and-bottleneck (stateful) | Lethal, resource-based, mature themes allowed |

---

## Ending types

An ending is typed on two required axes (the `Ending` model is `extra="forbid"`,
so no other fields, and there is no `ending.type`):

`ending.kind` (what mechanically happened, a closed set, `EndingKind`):

| Value | When to use |
|-------|-------------|
| `completion` | A successful ending that advances the series arc (the reader "wins" and the story world moves forward). |
| `success` | A satisfying win that does not advance the series arc. |
| `discovery` | The reader uncovers or learns something; outcome-neutral rather than a clear win or loss. |
| `setback` | A non-lethal bad outcome: the protagonist fails, retreats, or is otherwise set back, but survives. Allowed at 8-11 and above. |
| `capture` | A non-lethal entrapment outcome (caught, held, trapped). Allowed at 8-11 and above. |
| `death` | A lethal outcome. **Allowed only where the band's fail-state policy permits it**: never at 3-5 or 5-8. |

`ending.valence` (how it feels, independent of what happened, `Valence`):
`positive`, `neutral`, or `negative`.

Every ending also carries `ending.id` and `ending.title` (both non-empty
strings). The pre-schema single free-string `type` maps onto the two axes:
old `good` -> `kind: success` / `valence: positive`; old `neutral` ->
`kind: discovery` (or `setback`) / `valence: neutral`; old `failure` ->
`kind: setback` or `capture` / `valence: negative`.

## Series continuations: carried variables (Tier-2)

When a book is book 2+ of a `carries_state=true` series, any variable acquired in
an earlier book **initializes true in this book**, carried in from the sibling's
final state. This inverts acquisition branches: a branch that in book 1 gated on
"you do not have it yet" (`has_lantern == false`) is now unsatisfiable in book 2,
because `has_lantern` starts true. An unsatisfiable conditional branch is a hard
`L2-11` dead-branch error at the gate.

Do not copy book 1's acquisition branches into a continuation. Redesign them:

- Flip the condition into an always-satisfiable **carried-state gate** that reads
  the variable as already held (`has_lantern == true`), e.g. "you still have the
  lantern from before, so ...".
- Drop the now-redundant `set` effects that acquired the variable (it is already
  set on entry).

Only the acquisition branch of a carried variable needs this treatment; branches
that consume or check an already-held variable are unaffected. A quick check: any
condition of the form `<carried_var> == false` in a continuation book is almost
certainly a dead branch and must be redesigned, not copied.
