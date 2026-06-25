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

The `ending.type` field is a free string. Use the following conventions:

| Value | When to use |
|-------|-------------|
| `completion` | A successful ending that advances the series arc (the reader "wins" and the story world moves forward). |
| `good` | A satisfying ending that does not advance the series arc. |
| `neutral` | A non-advancing ending that is neither clearly positive nor negative. |
| `failure` | A non-death bad outcome: the protagonist fails, is captured, retreats, or is otherwise set back, but survives. Allowed at 8-11 and above. |
| `death` | A lethal outcome. **Allowed only where the band's fail-state policy permits it**: never at 3-5 or 5-8. |
