# Compliance report: the-salt-archive (filled)

- **Cell**: 16+ / long / prose (Wave 3)
- **Skeleton**: `skeletons/16+/the-salt-archive.json` (225 nodes, branch_and_bottleneck, tier 1, 54 endings)
- **Author model**: opus (Fable-outage routing)
- **Reviewer model**: opus (independent; verified graph dominance in python)
- **Disposition**: APPROVED (after a supervisor skeleton-metadata fix)

## Deterministic checks (final)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 170.6/node over 225 nodes (target 175, advisory 125-230, max 385)
findings=0 blocked=False safety_flagged=False
```

Zero RL-13 warnings (all 225 nodes in FK 7.5-10.5; the file declares tighter
flags than the 16+ ceiling: violence mild, scariness moderate, peril moderate).

## Independent review: 6 categories PASS, 1 REVISE (titles only)

An exceptionally disciplined fill. Reviewer verifications (via python
dominator analysis):

- **Character grounding holds route-neutrally**: Maren Coll, founder Elias
  Verrin, and last-contributor Nan Ostler are all introduced in `n_start`
  (the universal root) and reinforced at the p-gate dominators, so no
  convergence node asserts a fact a partial-route reader lacks.
- **Four beat/structure count-mismatches absorbed without a seam**: the two
  self-reported (p2 "three"/4 parents; p3 "both"/3 parents) plus two the
  reviewer found unreported (p1_gate "three"/4 choices; p2_gate "two"/3
  choices), all rendered count-neutral.
- All 54 endings match kind/valence; the 32-way "the sea holds its level"
  refrain is a genuinely varied chorus, not a template; zero body fragments.
- No PII/brand/IP; adult dread stays within literary bounds; "drowned" (125
  hits) always refers to rooms/records, never a person.

The single REVISE: **7 ending TITLES truncated mid-word**, inherited verbatim
from the skeleton metadata (the fill's ending-grammar pass covered bodies, not
titles, which are immutable structure for the author).

## Supervisor fix (skeleton + filled metadata)

Because the truncated titles are a pre-run **skeleton data defect** (structure
the fill cannot touch), the fix was applied at the metadata level in BOTH the
skeleton and the filled file (kept matched so integrity still shows
"only node bodies differ"). The 7 titles were completed from each ending's
content without inventing unknowable specifics:

- `mA_e2` -> "Sealed Around the Vows the Town Kept"
- `mB_e2` -> "Sealed Around the Pages"
- `mC_e2` -> "Sealed Around the Names of Saltmere"
- `mD_e2` -> "Sealed Around the Register of Births"
- `nA_e1` -> "Kept Distance: What Elias Verrin Left Unsaid"
- `nA_e2` -> "Refused the Page Elias Verrin Left"
- `nB_e1` -> "Kept Distance: The Last Voice in the Archive"

A scan of all 54 ending titles confirmed no other truncations. The skeleton
still passes `check_skeleton`; the filled file still passes both scripts.

## Supervisor adjudication

Approved. The prose fill was clean on every dimension; the only defect was
inherited skeleton metadata, now fixed in both artifacts. 13 of 14 stories
approved.

## Skeleton defect (fixed, not just filed)

`skeletons/16+/the-salt-archive.json`: 7 ending titles were truncated
mid-word, and four merge-node beats carried parent-count mismatches (p1_gate,
p2_gate, p2, p3). The titles are now fixed in the skeleton; the count beats
should be reworded in a future revision (the fill already handles them
count-neutrally).
